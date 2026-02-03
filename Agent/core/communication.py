import json
import logging
from typing import Dict, Any
from livekit import agents, rtc

logger = logging.getLogger(__name__)

async def publish_chat_event(room: rtc.Room, event_data: dict):
    """
    Publish structured chat event via LiveKit data channel
    """
    try:
        payload = json.dumps(event_data).encode('utf-8')
        await room.local_participant.publish_data(
            payload,
            topic="chat_events"
        )
    except Exception as e:
        logger.error(f"❌ Failed to publish chat event: {e}")

async def publish_user_message(room: rtc.Room, turn_id: str, content: str):
    """
    Publish user message event
    """
    await publish_chat_event(room, {
        "type": "user_message",
        "turn_id": turn_id,
        "content": content,
        "timestamp": agents.utils.time_ms()
    })

async def publish_assistant_delta(room: rtc.Room, turn_id: str, delta_text: str, seq: int):
    """
    Publish assistant delta event (streaming)
    """
    await publish_chat_event(room, {
        "type": "assistant_delta",
        "turn_id": turn_id,
        "content": delta_text,
        "seq": seq,
        "timestamp": agents.utils.time_ms()
    })

async def publish_assistant_final(room: rtc.Room, turn_id: str, full_content: str):
    """
    Publish assistant final event (complete response)
    """
    await publish_chat_event(room, {
        "type": "assistant_final",
        "turn_id": turn_id,
        "content": full_content,
        "timestamp": agents.utils.time_ms()
    })
