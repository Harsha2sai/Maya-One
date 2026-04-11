"""Voice/transcription and response sanitization helpers for AgentOrchestrator."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from core.communication import publish_agent_thinking, publish_user_message

logger = logging.getLogger(__name__)


class VoiceCoordinator:
    """Owns voice-specific normalization, guardrails, and event handling."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    def normalize_voice_transcription_for_routing(self, message: str) -> tuple[str, bool]:
        text = str(message or "")
        if not text:
            return "", False
        normalized = text
        changed = False
        for garbled, corrected in self._owner._VOICE_TRANSCRIPTION_NORMALIZATIONS.items():
            updated = re.sub(
                rf"\b{re.escape(garbled)}\b",
                corrected,
                normalized,
                flags=re.IGNORECASE,
            )
            if updated != normalized:
                normalized = updated
                changed = True
        return normalized, changed

    @staticmethod
    def should_use_deep_research_voice(query: str, *, deep_keywords: tuple[str, ...]) -> bool:
        text = str(query or "").strip().lower()
        if not text:
            return False
        if any(keyword in text for keyword in deep_keywords):
            return True
        words = re.findall(r"\b[\w'-]+\b", text)
        return len(words) >= 25

    def is_voice_continuation_fragment(
        self,
        *,
        routing_text: str,
        origin: str,
        chat_ctx_messages: List[Any],
        short_command_allowlist: set[str],
        continuation_markers: set[str],
        action_second_token_allowlist: set[str],
    ) -> bool:
        if str(origin or "").strip().lower() != "voice":
            return False
        if not chat_ctx_messages:
            return False
        normalized = str(routing_text or "").strip().lower()
        if not normalized:
            return False
        if normalized in short_command_allowlist:
            return False

        tokens = re.findall(r"\b[\w'-]+\b", normalized)
        if not tokens or len(tokens) > 6:
            return False
        if len(tokens) == 1 and tokens[0] in short_command_allowlist:
            return False
        if tokens[0] not in continuation_markers:
            return False
        if len(tokens) > 1 and tokens[1] in action_second_token_allowlist:
            return False

        for message in reversed(chat_ctx_messages):
            if self._owner._message_role_value(message) != "assistant":
                continue
            if self._owner._message_content_to_text(message):
                return True
        return False

    def parse_legacy_function_call(self, text: str) -> Optional[tuple[str, Dict[str, Any]]]:
        if not text:
            return None

        match = re.search(
            r"<function>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(\{.*?\})?\s*</function>",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            flat_match = re.search(
                r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=)?\s*(\{.*\})\s*$",
                text.strip(),
                re.IGNORECASE | re.DOTALL,
            )
            if not flat_match:
                return None
            match = flat_match

        tool_name = (match.group(1) or "").strip()
        args_blob = (match.group(2) or "").strip()
        args: Dict[str, Any] = {}
        if args_blob:
            try:
                parsed = json.loads(args_blob)
                if isinstance(parsed, dict):
                    args = parsed
            except Exception:
                query_match = re.search(r'"query"\s*:\s*"([^"]+)"', args_blob)
                if query_match:
                    args = {"query": query_match.group(1)}

        if not tool_name:
            return None
        return (tool_name, args)

    @staticmethod
    def is_tool_call_generation_error(err: Exception) -> bool:
        msg = str(err or "").lower()
        patterns = (
            "failed to call a function",
            "tool call validation failed",
            "attempted to call tool",
            "not in request.tools",
            "invalid tool",
            "invalid function call",
        )
        return any(p in msg for p in patterns)

    def normalize_tool_invocation(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        normalized_name = str(tool_name or "").strip()
        normalized_args: Dict[str, Any] = dict(args or {})

        def _merge_json_blob(blob: str) -> None:
            blob = (blob or "").strip()
            if not blob or not blob.startswith("{"):
                return
            try:
                parsed = json.loads(blob)
                if isinstance(parsed, dict):
                    normalized_args.update(parsed)
                    return
            except Exception:
                pass

            query_match = re.search(r'"query"\s*:\s*"([^"]+)"', blob)
            if query_match:
                normalized_args.setdefault("query", query_match.group(1))

        if "=" in normalized_name:
            left, right = normalized_name.split("=", 1)
            if left.strip():
                normalized_name = left.strip()
                _merge_json_blob(right)

        brace_idx = normalized_name.find("{")
        if brace_idx > 0 and normalized_name.endswith("}"):
            embedded_blob = normalized_name[brace_idx:]
            normalized_name = normalized_name[:brace_idx].strip()
            _merge_json_blob(embedded_blob)

        return normalized_name, normalized_args

    @staticmethod
    def strip_legacy_function_markup(text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(
            r"<function>\s*[a-zA-Z_][a-zA-Z0-9_]*\s*(?:\{.*?\})?\s*</function>",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return cleaned.strip()

    def sanitize_response(self, text: str) -> str:
        if not text:
            return ""

        cleaned = self.strip_legacy_function_markup(text)
        leak_detected = False

        closed_tag_pattern = re.compile(
            r"<([a-zA-Z_][\w-]*)>\s*\{[\s\S]*?\}\s*</\1>",
            flags=re.IGNORECASE,
        )
        open_tag_pattern = re.compile(
            r"<([a-zA-Z_][\w-]*)>\s*\{[\s\S]*?\}(?:\s|$)",
            flags=re.IGNORECASE,
        )

        if closed_tag_pattern.search(cleaned):
            leak_detected = True
            cleaned = closed_tag_pattern.sub(" ", cleaned)

        if open_tag_pattern.search(cleaned):
            leak_detected = True
            cleaned = open_tag_pattern.sub(" ", cleaned)

        if leak_detected:
            logger.warning("tool_markup_leak_detected")

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def sanitize_research_voice_for_tts(
        self,
        voice: str,
        display: str,
        *,
        voice_mode: str = "brief",
    ) -> tuple[str, str]:
        from core.research.result_synthesizer import ResultSynthesizer

        def _has_json_signatures(text: str) -> bool:
            sample = str(text or "")
            return bool(
                re.search(r'(?i)"?\b(display|voice)\b"?\s*:', sample)
                or re.search(r"[{}]", sample)
            )

        raw_voice = str(voice or "").strip()
        if not raw_voice:
            display_fallback = ResultSynthesizer._normalize_voice(
                ResultSynthesizer._voice_from_display(display, voice_mode=voice_mode),
                voice_mode=voice_mode,
            )
            if display_fallback:
                return display_fallback, "display_fallback"
            return "", "empty"

        direct = ResultSynthesizer._normalize_voice(
            self.sanitize_response(raw_voice),
            voice_mode=voice_mode,
        )
        if direct and not _has_json_signatures(direct):
            return direct, "direct"

        cleaned_source = re.sub(r'(?i)"?\b(display|voice)\b"?\s*:\s*', " ", raw_voice)
        cleaned_source = re.sub(r"[{}\"]", " ", cleaned_source)
        cleaned_source = re.sub(r"(?im)^\s*sources?\s*:.*$", " ", cleaned_source)
        cleaned_source = re.sub(r"\s+", " ", cleaned_source).strip()
        cleaned = ResultSynthesizer._normalize_voice(
            self.sanitize_response(cleaned_source),
            voice_mode=voice_mode,
        )
        if cleaned and not _has_json_signatures(cleaned):
            return cleaned, "cleaned"

        display_fallback = ResultSynthesizer._normalize_voice(
            ResultSynthesizer._voice_from_display(display, voice_mode=voice_mode),
            voice_mode=voice_mode,
        )
        if display_fallback and not _has_json_signatures(display_fallback):
            return display_fallback, "display_fallback"
        return "", "empty"

    @staticmethod
    def parse_multi_app(app_phrase: str) -> List[str]:
        phrase = (app_phrase or "").strip().lower().strip(" .,!?:;")
        if not phrase:
            return []

        parts = [p.strip() for p in re.split(r"\s*(?:,|&|\band\b)\s*", phrase) if p.strip()]
        if len(parts) < 2:
            return []

        command_map = {
            "firefox": "firefox",
            "chrome": "google-chrome",
            "google chrome": "google-chrome",
            "chromium": "chromium-browser",
            "brave": "brave-browser",
            "edge": "microsoft-edge",
            "calculator": "gnome-calculator",
            "files": "nautilus",
            "file manager": "nautilus",
            "terminal": "gnome-terminal",
        }

        commands: List[str] = []
        for raw_part in parts:
            part = re.sub(r"^\b(the|my)\b\s+", "", raw_part).strip()
            part = re.sub(r"\s+\b(app|application)\b$", "", part).strip()
            cmd = command_map.get(part)
            if not cmd:
                return []
            commands.append(cmd)

        deduped = list(dict.fromkeys(commands))
        return deduped if len(deduped) > 1 else []

    def on_transcription_received(self, transcription: Any) -> None:
        try:
            if transcription.is_final and transcription.participant and transcription.participant.is_local:
                turn_id = self._owner._start_new_turn(transcription.text)
                self._owner._spawn_background_task(
                    publish_user_message(self._owner.room, turn_id, transcription.text)
                )
                self._owner._spawn_background_task(
                    publish_agent_thinking(self._owner.room, turn_id, "thinking")
                )
        except Exception as e:
            logger.error("❌ Error handling transcription: %s", e)

    async def process_chat_message(self, text: str) -> None:
        try:
            logger.info("📝 Adding user text to agent context: %s", text)
            if hasattr(self._owner.agent, "chat_ctx") and hasattr(self._owner.agent, "update_chat_ctx"):
                new_ctx = self._owner.agent.chat_ctx.copy()
                new_ctx.add_message(role="user", content=text)
                await self._owner.agent.update_chat_ctx(new_ctx)
                logger.info("✅ Chat context updated")
            logger.info("🤖 Triggering agent reply...")
            self._owner.session.generate_reply()
        except Exception as e:
            logger.error("❌ Error in process_chat_message: %s", e)

    def on_data_received(self, *args: Any) -> None:
        try:
            data, topic = None, None
            if len(args) >= 4:
                data, topic = args[0], args[3]
            elif len(args) == 1:
                obj = args[0]
                data = getattr(obj, "data", None)
                topic = getattr(obj, "topic", None)
            if (topic == "chat" or topic == "lk.chat") and data:
                text = data.decode("utf-8")
                logger.info("📩 Chat message received: %s", text)
                self._owner._spawn_background_task(self.process_chat_message(text))
        except Exception as e:
            logger.error("❌ Error handling data message: %s", e)

    @staticmethod
    def parse_client_config(participant: Any) -> Dict[str, Any]:
        if not participant.metadata:
            return {}
        try:
            config = json.loads(participant.metadata)
            logger.info("🔧 Parsed client config: %s", config)
            return config
        except Exception as e:
            logger.warning("⚠️ Failed to parse metadata: %s", e)
            return {}
