"""Tests for TurnContext dataclass."""
from unittest.mock import MagicMock

from core.orchestrator.turn_context import TurnContext


def test_basic_construction():
    ctx = TurnContext(message="hello", user_id="u1", tool_context=None)
    assert ctx.message == "hello"
    assert ctx.user_id == "u1"
    assert ctx.origin == "chat"
    assert ctx.route == ""
    assert ctx.turn_id != ""


def test_with_route_returns_new_instance():
    ctx = TurnContext(message="hello", user_id="u1", tool_context=None)
    ctx2 = ctx.with_route("research")
    assert ctx2.route == "research"
    assert ctx.route == ""


def test_from_handle_message_args_basic():
    ctx = TurnContext.from_handle_message_args(
        message="what time is it",
        user_id="u2",
        tool_context=None,
        origin="voice",
    )
    assert ctx.message == "what time is it"
    assert ctx.origin == "voice"
    assert ctx.session_id == ""
    assert ctx.trace_id == ""


def test_from_handle_message_args_extracts_session_id():
    mock_ctx = MagicMock()
    mock_ctx.session_id = "sess-123"
    mock_ctx.trace_id = "trace-456"
    ctx = TurnContext.from_handle_message_args(
        message="hello",
        user_id="u3",
        tool_context=mock_ctx,
    )
    assert ctx.session_id == "sess-123"
    assert ctx.trace_id == "trace-456"


def test_from_handle_message_args_none_tool_context():
    ctx = TurnContext.from_handle_message_args(
        message="hi",
        user_id="u4",
        tool_context=None,
    )
    assert ctx.session_id == ""
    assert ctx.trace_id == ""


def test_turn_id_unique_per_instance():
    ctx1 = TurnContext(message="a", user_id="u", tool_context=None)
    ctx2 = TurnContext(message="a", user_id="u", tool_context=None)
    assert ctx1.turn_id != ctx2.turn_id


def test_origin_default():
    ctx = TurnContext(message="x", user_id="u", tool_context=None)
    assert ctx.origin == "chat"
