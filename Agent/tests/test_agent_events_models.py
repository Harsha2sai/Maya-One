from __future__ import annotations

import pytest

from core.events.agent_events import SCHEMA_VERSION, chat_event_json_schema, validate_chat_event_payload


def test_validate_user_message_payload() -> None:
    payload = validate_chat_event_payload(
        {
            "type": "user_message",
            "schema_version": SCHEMA_VERSION,
            "turn_id": "t1",
            "content": "hello",
            "timestamp": 123,
        }
    )
    assert payload["type"] == "user_message"
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["turn_id"] == "t1"


def test_tool_execution_payload_supports_tool_alias() -> None:
    payload = validate_chat_event_payload(
        {
            "type": "tool_execution",
            "schema_version": SCHEMA_VERSION,
            "turn_id": "t2",
            "tool_name": "web_search",
            "tool": "web_search",
            "status": "started",
            "timestamp": 456,
        }
    )
    assert payload["tool_name"] == "web_search"
    assert payload["tool"] == "web_search"


def test_unknown_event_type_fails_validation() -> None:
    with pytest.raises(Exception):
        validate_chat_event_payload(
            {
                "type": "unknown_event",
                "schema_version": SCHEMA_VERSION,
                "timestamp": 1,
            }
        )


def test_missing_schema_version_fails_validation() -> None:
    with pytest.raises(Exception):
        validate_chat_event_payload(
            {
                "type": "agent_thinking",
                "turn_id": "t3",
                "state": "thinking",
                "timestamp": 789,
            }
        )


def test_json_schema_contains_discriminator_and_schema_version() -> None:
    schema = chat_event_json_schema()
    schema_text = str(schema)
    assert "discriminator" in schema_text
    assert "schema_version" in schema_text


def test_validate_research_result_payload() -> None:
    payload = validate_chat_event_payload(
        {
            "type": "research_result",
            "schema_version": SCHEMA_VERSION,
            "turn_id": "t5",
            "query": "latest ai news",
            "summary": "Here are the key highlights.",
            "sources": [
                {
                    "title": "Source A",
                    "url": "https://example.com/a",
                    "domain": "example.com",
                    "snippet": "snippet",
                    "provider": "tavily",
                }
            ],
            "timestamp": 999,
        }
    )
    assert payload["type"] == "research_result"
    assert payload["turn_id"] == "t5"
    assert payload["sources"][0]["provider"] == "tavily"


def test_validate_media_result_payload() -> None:
    payload = validate_chat_event_payload(
        {
            "type": "media_result",
            "schema_version": SCHEMA_VERSION,
            "turn_id": "m1",
            "action": "play",
            "provider": "spotify",
            "track_name": "Song A",
            "artist": "Artist A",
            "track_url": "https://open.spotify.com/track/abc",
            "timestamp": 111,
        }
    )
    assert payload["type"] == "media_result"
    assert payload["provider"] == "spotify"
    assert payload["track_name"] == "Song A"


def test_validate_system_result_payload() -> None:
    payload = validate_chat_event_payload(
        {
            "type": "system_result",
            "schema_version": SCHEMA_VERSION,
            "action_type": "SCREENSHOT",
            "success": True,
            "message": "Saved screenshot.",
            "detail": "/tmp/screen.png",
            "rollback_available": False,
            "timestamp": 222,
        }
    )
    assert payload["type"] == "system_result"
    assert payload["action_type"] == "SCREENSHOT"
    assert payload["success"] is True


def test_validate_confirmation_required_payload() -> None:
    payload = validate_chat_event_payload(
        {
            "type": "confirmation_required",
            "schema_version": SCHEMA_VERSION,
            "action_type": "FILE_DELETE",
            "description": "Delete test.txt",
            "destructive": True,
            "timeout_seconds": 30,
            "timestamp": 333,
            "trace_id": "trace-confirm",
        }
    )
    assert payload["type"] == "confirmation_required"
    assert payload["destructive"] is True
    assert payload["trace_id"] == "trace-confirm"


def test_validate_confirmation_response_payload() -> None:
    payload = validate_chat_event_payload(
        {
            "type": "confirmation_response",
            "schema_version": SCHEMA_VERSION,
            "confirmed": False,
            "trace_id": "trace-reply",
            "timestamp": 444,
        }
    )
    assert payload["type"] == "confirmation_response"
    assert payload["confirmed"] is False
    assert payload["trace_id"] == "trace-reply"
