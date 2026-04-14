"""LiveKit voice transcription to ProjectModeOrchestrator bridge."""
from __future__ import annotations

from typing import Optional


class VoiceProjectBridge:
    """
    Bridges final voice transcripts to ProjectModeOrchestrator.

    Behavior:
    - If no project is active, only explicit project intents are handled.
    - If a project is active, free-form utterances are treated as requirements.
    - Project control shortcuts are recognized in voice form (next/done/cancel/status).
    """

    _NEXT_ALIASES = {"next", "done", "continue", "proceed"}
    _STATUS_ALIASES = {"status", "project status"}
    _CANCEL_ALIASES = {"cancel", "stop project", "end project", "project cancel"}

    def __init__(self, project_orchestrator, buddy):
        self.project = project_orchestrator
        self.buddy = buddy
        # Backward-compat testing field; project mode is global/singleton now.
        self._active_session_id: Optional[str] = None

    async def on_transcript(self, text: str, is_final: bool) -> Optional[str]:
        """
        Route final transcript to project mode when applicable.

        Returns:
            Response text when handled, or None when transcript is unrelated to project mode.
        """
        if not is_final:
            return None

        utterance = str(text or "").strip()
        if not utterance:
            return None

        command = self._normalize_project_command(utterance)
        if command is not None:
            response = await self._dispatch_project_command(command)
            self._active_session_id = "project_mode" if self.is_active else None
            return response

        if not self.is_active:
            return None

        response = await self.project.add_requirement(utterance)
        self._active_session_id = "project_mode"
        return response

    async def get_prd(self) -> Optional[str]:
        """Return current project PRD text when available."""
        active = getattr(self.project, "_active", None)
        prd = getattr(active, "prd", None) if active is not None else None
        if not prd:
            return None
        if hasattr(prd, "to_markdown"):
            return prd.to_markdown()
        return str(prd)

    async def end_session(self) -> Optional[str]:
        """Cancel active project mode session if one exists."""
        if not self.is_active:
            return None
        self._active_session_id = None
        return await self.project.cancel()

    @property
    def is_active(self) -> bool:
        """Check if project mode is currently active."""
        checker = getattr(self.project, "is_active", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        return bool(getattr(self.project, "_active", None))

    def _normalize_project_command(self, utterance: str) -> Optional[str]:
        text = utterance.strip()
        lower = text.lower()

        if lower.startswith("/project"):
            return text

        if lower.startswith("start project "):
            name = text[len("start project ") :].strip()
            return f"/project start {name}" if name else "/project start voice_session"

        if lower == "project":
            return "/project status"

        if lower.startswith("project "):
            rest = text[len("project ") :].strip()
            if not rest:
                return "/project status"
            if rest.lower().startswith(("start ", "req ", "next", "status", "cancel")):
                return f"/project {rest}"
            return f"/project start {rest}"

        if not self.is_active:
            return None

        if lower in self._NEXT_ALIASES:
            return "/project next"
        if lower in self._STATUS_ALIASES:
            return "/project status"
        if lower in self._CANCEL_ALIASES:
            return "/project cancel"

        return None

    async def _dispatch_project_command(self, raw: str) -> str:
        body = raw[1:] if raw.startswith("/") else raw
        parts = body.split(maxsplit=2)
        if len(parts) < 2 or parts[0].lower() != "project":
            return "Project mode commands: /project start|req|next|status|cancel"

        sub = parts[1].strip().lower()
        arg = parts[2].strip() if len(parts) > 2 else ""

        if sub == "start":
            return await self.project.start(arg or "voice_session")
        if sub == "req":
            if not arg:
                return "Usage: /project req <requirement>"
            return await self.project.add_requirement(arg)
        if sub == "next":
            return await self.project.advance()
        if sub == "status":
            return await self.project.status()
        if sub == "cancel":
            return await self.project.cancel()

        return (
            "Project mode commands:\n"
            "  /project start <name>\n"
            "  /project req <requirement>\n"
            "  /project next\n"
            "  /project status\n"
            "  /project cancel"
        )
