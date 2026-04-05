"""
MediaHandler - Handles media route execution.
Extracted from ChatResponseMixin (Phase 24).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from core.observability.trace_context import current_trace_id
from core.response.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class MediaHandler:
    """Owns media intent execution and response formatting."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    async def handle_media_route(
        self,
        *,
        message: str,
        user_id: str,
        tool_context: Any,
    ) -> Any:
        try:
            media_command = await self._owner._resolve_media_query_from_preferences(message, user_id)
            session_id = (
                getattr(tool_context, "session_id", None)
                or self._owner._current_session_id
                or getattr(getattr(self._owner, "room", None), "name", None)
                or "console_session"
            )
            trace_id = (
                getattr(tool_context, "trace_id", None)
                or current_trace_id()
                or str(uuid.uuid4())
            )
            handoff_target = self._owner._consume_handoff_signal(
                target_agent="media",
                execution_mode="inline",
                reason="router_media_play",
                context_hint=str(message or "")[:160],
            )
            handoff_request = self._owner._build_handoff_request(
                target_agent=handoff_target,
                message=media_command,
                user_id=user_id,
                execution_mode="inline",
                intent="media_play",
                tool_context=tool_context,
                handoff_reason="router_media_play",
            )
            handoff_result = await self._owner._handoff_manager.delegate(handoff_request)

            if handoff_result.status == "needs_followup":
                followup_payload = dict(handoff_result.structured_payload or {})
                if followup_payload.get("url"):
                    await self._owner._publish_runtime_topic_event(
                        "maya/system/spotify/auth_url",
                        {
                            "type": "spotify_auth_url",
                            "platform": str(followup_payload.get("platform") or "desktop"),
                            "url": str(followup_payload.get("url") or ""),
                            "state": str(followup_payload.get("state") or ""),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "source": "orchestrator_media_handoff",
                        },
                    )
                summary_text = (
                    str(handoff_result.user_visible_text or "").strip()
                    or str(followup_payload.get("message") or "").strip()
                    or "Spotify needs to be connected first."
                )
                response = ResponseFormatter.build_response(
                    display_text=summary_text,
                    voice_text=summary_text,
                    mode="normal",
                    confidence=0.7,
                    structured_data={
                        "_media_followup": followup_payload,
                        "_handoff_result": followup_payload,
                    },
                )
                logger.info(
                    "media_followup provider=%s requires_auth=%s trace_id=%s",
                    str(followup_payload.get("provider") or "spotify"),
                    bool(followup_payload.get("requires_auth")),
                    trace_id,
                )
                return self._owner._tag_response_with_routing_type(response, "direct_action")

            if handoff_result.status in {"failed", "rejected"}:
                logger.warning(
                    "media_handoff_fallback_to_legacy trace_id=%s status=%s error_code=%s",
                    trace_id,
                    handoff_result.status,
                    handoff_result.error_code,
                )
                media_agent = self._owner._resolve_media_agent()
                media_result = await media_agent.run(
                    command=media_command,
                    user_id=user_id,
                    session_id=session_id,
                    trace_id=trace_id,
                )
                media_payload = {
                    "action": media_result.action,
                    "provider": media_result.provider,
                    "track_name": media_result.track.title if media_result.track else "",
                    "artist": media_result.track.artist if media_result.track else "",
                    "album_art_url": media_result.track.album_art_url if media_result.track else "",
                    "track_url": media_result.track.url if media_result.track else "",
                    "trace_id": trace_id,
                }
                summary_text = str(media_result.message or "").strip() or "I was unable to complete that."
                structured_data = {"_media_result": media_payload}
            else:
                media_payload = dict(handoff_result.structured_payload or {})
                summary_text = (
                    str(handoff_result.user_visible_text or "").strip()
                    or str(media_payload.get("message") or "").strip()
                    or "I was unable to complete that."
                )
                structured_data = {
                    "_media_result": {
                        "action": str(media_payload.get("action") or ""),
                        "provider": str(media_payload.get("provider") or ""),
                        "track_name": str(media_payload.get("track_name") or ""),
                        "artist": str(media_payload.get("artist") or ""),
                        "album_art_url": str(media_payload.get("album_art_url") or ""),
                        "track_url": str(media_payload.get("track_url") or ""),
                        "trace_id": str(media_payload.get("trace_id") or trace_id),
                    },
                    "_handoff_result": media_payload,
                }
                logger.info(
                    "media_result action=%s provider=%s success=%s",
                    str(media_payload.get("action") or ""),
                    str(media_payload.get("provider") or ""),
                    bool(media_payload.get("success")),
                )
            response = ResponseFormatter.build_response(
                display_text=summary_text,
                voice_text=summary_text,
                mode="normal",
                confidence=0.9 if structured_data["_media_result"].get("provider") else 0.5,
                structured_data=structured_data,
            )
            self._owner.turn_state["pending_system_action_result"] = summary_text
            return self._owner._tag_response_with_routing_type(response, "direct_action")
        except Exception as e:
            logger.error("media_route_failed error=%s", e, exc_info=True)
            return self._owner._tag_response_with_routing_type(
                ResponseFormatter.build_response("I was unable to complete that."),
                "direct_action",
            )
