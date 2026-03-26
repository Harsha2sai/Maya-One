import json
import logging
from typing import Any

from core.events.agent_events import SCHEMA_VERSION, validate_chat_event_payload
from core.observability.trace_context import current_trace_id
from core.response.response_formatter import ResponseFormatter
from livekit import agents, rtc

logger = logging.getLogger(__name__)


def _with_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    event_payload = dict(payload or {})
    event_payload.setdefault("schema_version", SCHEMA_VERSION)
    event_payload.setdefault("timestamp", agents.utils.time_ms())
    trace_id = str(event_payload.get("trace_id") or "").strip() or current_trace_id()
    event_payload["trace_id"] = trace_id
    return event_payload


async def publish_chat_event(room: rtc.Room, event_data: dict[str, Any]) -> bool:
    """Publish validated structured event over LiveKit data channel."""
    try:
        normalized = validate_chat_event_payload(_with_envelope(event_data))
    except Exception as e:
        logger.error(
            "chat_event_validation_failed type=%s error=%s",
            str((event_data or {}).get("type") or "unknown"),
            e,
        )
        return False

    try:
        payload = json.dumps(normalized).encode("utf-8")
        await room.local_participant.publish_data(payload, topic="chat_events")
        logger.info(
            "chat_event_published topic=chat_events type=%s turn_id=%s",
            str(normalized.get("type") or ""),
            str(normalized.get("turn_id") or ""),
        )
        return True
    except Exception as e:
        logger.error("❌ Failed to publish chat event: %s", e)
        return False


async def publish_agent_response_text(room: rtc.Room, response_text: Any):
    """
    Publish assistant response as a text-stream compatible packet for Flutter
    listeners registered on topic `lk.agent.response`.
    """
    try:
        resp = ResponseFormatter.normalize_response(response_text)
        await room.local_participant.send_text(
            resp.display_text,
            topic="lk.agent.response",
        )
    except Exception as e:
        logger.error(f"❌ Failed to publish lk.agent.response text: {e}")


async def publish_user_message(room: rtc.Room, turn_id: str, content: str) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "user_message",
            "turn_id": turn_id,
            "content": content,
        },
    )


async def publish_assistant_delta(room: rtc.Room, turn_id: str, delta_text: str, seq: int) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "assistant_delta",
            "turn_id": turn_id,
            "content": delta_text,
            "seq": seq,
        },
    )


async def publish_assistant_final(room: rtc.Room, turn_id: str, full_content: Any) -> bool:
    resp = ResponseFormatter.normalize_response(full_content)
    payload = {
        "type": "assistant_final",
        "turn_id": turn_id,
        "content": resp.display_text,
        "voice_text": resp.voice_text,
        "sources": [s.model_dump() if hasattr(s, "model_dump") else s.dict() for s in (resp.sources or [])],
        "tool_invocations": [
            t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in (resp.tool_invocations or [])
        ],
        "mode": resp.mode,
        "memory_updated": resp.memory_updated,
        "confidence": resp.confidence,
        "structured_data": resp.structured_data or {},
    }
    return await publish_chat_event(room, payload)


async def publish_agent_thinking(room: rtc.Room, turn_id: str, state: str) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "agent_thinking",
            "turn_id": turn_id,
            "state": state,
        },
    )


async def publish_tool_execution(
    room: rtc.Room,
    turn_id: str,
    tool_name: str,
    status: str,
    *,
    message: str | None = None,
    task_id: str | None = None,
    conversation_id: str | None = None,
) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "tool_execution",
            "turn_id": turn_id,
            "tool_name": tool_name,
            "tool": tool_name,  # compatibility alias
            "status": status,
            "message": message,
            "task_id": task_id,
            "conversation_id": conversation_id,
        },
    )


async def publish_agent_speaking(room: rtc.Room, turn_id: str, status: str) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "agent_speaking",
            "turn_id": turn_id,
            "status": status,
        },
    )


async def publish_turn_complete(room: rtc.Room, turn_id: str, status: str) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "turn_complete",
            "turn_id": turn_id,
            "status": status,
        },
    )


async def publish_error_event(
    room: rtc.Room,
    *,
    turn_id: str | None,
    message: str,
    code: str | None = None,
) -> bool:
    safe_message = str(message or "").strip() or "I ran into an issue while processing that. Please try again."
    return await publish_chat_event(
        room,
        {
            "type": "error",
            "turn_id": turn_id,
            "message": safe_message,
            "code": code,
        },
    )


async def publish_research_result(
    room: rtc.Room,
    *,
    turn_id: str,
    query: str,
    summary: str,
    sources: list[dict[str, Any]],
    trace_id: str | None = None,
    task_id: str | None = None,
    conversation_id: str | None = None,
) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "research_result",
            "turn_id": turn_id,
            "query": str(query or "").strip(),
            "summary": str(summary or "").strip(),
            "sources": list(sources or []),
            "trace_id": trace_id,
            "task_id": task_id,
            "conversation_id": conversation_id,
        },
    )


async def publish_media_result(
    room: rtc.Room,
    *,
    turn_id: str,
    action: str,
    provider: str,
    track_name: str | None = None,
    artist: str | None = None,
    album_art_url: str | None = None,
    track_url: str | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
    conversation_id: str | None = None,
) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "media_result",
            "turn_id": turn_id,
            "action": str(action or "").strip(),
            "provider": str(provider or "").strip(),
            "track_name": str(track_name or "").strip() or None,
            "artist": str(artist or "").strip() or None,
            "album_art_url": str(album_art_url or "").strip() or None,
            "track_url": str(track_url or "").strip() or None,
            "trace_id": trace_id,
            "task_id": task_id,
            "conversation_id": conversation_id,
        },
    )


async def publish_system_result(
    room: rtc.Room,
    *,
    turn_id: str | None = None,
    action_type: str,
    success: bool,
    message: str,
    detail: str = "",
    rollback_available: bool = False,
    trace_id: str | None = None,
    task_id: str | None = None,
    conversation_id: str | None = None,
) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "system_result",
            "turn_id": turn_id,
            "action_type": str(action_type or "").strip(),
            "success": bool(success),
            "message": str(message or "").strip(),
            "detail": str(detail or "").strip(),
            "rollback_available": bool(rollback_available),
            "trace_id": trace_id,
            "task_id": task_id,
            "conversation_id": conversation_id,
        },
    )


async def publish_confirmation_required(
    room: rtc.Room,
    *,
    action_type: str,
    description: str,
    destructive: bool,
    timeout_seconds: int = 30,
    trace_id: str | None = None,
) -> bool:
    return await publish_chat_event(
        room,
        {
            "type": "confirmation_required",
            "action_type": str(action_type or "").strip(),
            "description": str(description or "").strip(),
            "destructive": bool(destructive),
            "timeout_seconds": int(timeout_seconds),
            "trace_id": trace_id,
        },
    )
