"""Handoff-contract wrapper for Maya's existing media runtime."""

from __future__ import annotations

from typing import Any

from core.agents.base import SpecializedAgent
from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult
from core.media.media_agent import MediaAgent


class MediaAgentHandler(SpecializedAgent):
    def __init__(self, media_agent: MediaAgent | None = None) -> None:
        super().__init__("media")
        self._media_agent = media_agent or MediaAgent()

    async def can_accept(self, request: AgentHandoffRequest) -> AgentCapabilityMatch:
        confidence = 1.0 if str(request.intent or "").strip().lower() == "media_play" else 0.0
        return AgentCapabilityMatch(
            agent_name=self.name,
            confidence=confidence,
            reason="media_play_intent" if confidence >= 1.0 else "intent_not_media",
            hard_constraints_passed=confidence >= 1.0 and bool(str(request.user_text or "").strip()),
        )

    async def handle(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        metadata = dict(request.metadata or {})
        user_id = str(metadata.get("user_id") or "unknown")
        session_id = str(
            metadata.get("session_id")
            or request.conversation_id
            or metadata.get("conversation_id")
            or "console_session"
        )
        platform = str(metadata.get("platform") or "desktop")
        lowered_text = str(request.user_text or "").strip().lower()
        explicit_spotify = "spotify" in lowered_text

        if explicit_spotify and not self._media_agent.is_spotify_connected(user_id):
            auth_result = await self._media_agent.spotify.prepare_spotify_auth(
                user_id=user_id,
                platform=platform,
            )
            auth_payload = {
                "requires_auth": True,
                "provider": "spotify",
                "platform": str(auth_result.get("platform") or platform),
                "url": str(auth_result.get("url") or ""),
                "state": str(auth_result.get("state") or ""),
                "message": str(
                    auth_result.get("message")
                    or "Spotify needs to be connected first."
                ),
                "code": str(auth_result.get("code") or "spotify_auth_required"),
            }
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=self.name,
                status="needs_followup",
                user_visible_text="Spotify needs to be connected first. I sent the auth link.",
                voice_text="Spotify needs to be connected first. I sent the auth link.",
                structured_payload=auth_payload,
                next_action="respond",
                error_code=None,
                error_detail=None,
            )

        parsed = self._media_agent.router.parse(request.user_text)
        if (
            parsed.action in {"play", "search", "recommend", "queue"}
            and not explicit_spotify
            and not self._media_agent.is_spotify_connected(user_id)
        ):
            media_result = await self._media_agent.youtube.execute(parsed, user_id)
        else:
            media_result = await self._media_agent.run(
                command=request.user_text,
                user_id=user_id,
                session_id=session_id,
                trace_id=request.trace_id,
            )

        payload: dict[str, Any] = media_result.to_event_payload()
        payload.update(
            {
                "success": bool(media_result.success),
                "message": str(media_result.message or ""),
                "trace_id": request.trace_id,
            }
        )
        return AgentHandoffResult(
            handoff_id=request.handoff_id,
            trace_id=request.trace_id,
            source_agent=self.name,
            status="completed",
            user_visible_text=str(media_result.message or "").strip() or "I was unable to complete that.",
            voice_text=str(media_result.message or "").strip() or "I was unable to complete that.",
            structured_payload=payload,
            next_action="respond",
            error_code=None,
            error_detail=None,
            metadata={"provider": media_result.provider},
        )
