import pytest
from unittest.mock import AsyncMock, MagicMock

from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.response.agent_response import ToolInvocation


@pytest.fixture
def orchestrator():
    return AgentOrchestrator(MagicMock(), MagicMock())


FACTUAL_QUERIES = [
    "who is the prime minister of india",
    "who is the pm of india",
    "who is the ceo of openai",
    "what is quantum computing",
    "who founded microsoft",
]


def test_fastpath_next_song_matches_media_shell(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("next song", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.args["command"] == "playerctl next"
    assert intent.group == "media"


def test_fastpath_change_song_matches_media_shell(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("change song", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.args["command"] == "playerctl next"


def test_fastpath_previous_song_matches_media_shell(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("previous song", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.args["command"] == "playerctl previous"


def test_fastpath_play_next_matches_media_shell(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("play next", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.args["command"] == "playerctl next"
    assert intent.group == "media"


def test_fastpath_play_previous_matches_media_shell(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("play previous", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.args["command"] == "playerctl previous"
    assert intent.group == "media"


def test_fastpath_pause_matches_media_shell(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("pause music", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.args["command"] == "playerctl pause"


def test_fastpath_resume_matches_media_shell(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("resume music", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.args["command"] == "playerctl play"


def test_fastpath_open_youtube_matches_open_app(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("open youtube", origin="voice")
    assert intent is not None
    assert intent.tool == "open_app"
    assert intent.args["app_name"] == "youtube"


def test_fastpath_open_youtube_with_punctuation_matches_youtube_group(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("Open YouTube.", origin="voice")
    assert intent is not None
    assert intent.group == "youtube"
    assert intent.args["app_name"] == "youtube"


def test_fastpath_youtube_search_extracts_query(orchestrator):
    intent = orchestrator._detect_direct_tool_intent(
        "search youtube for llm updates",
        origin="voice",
    )
    assert intent is not None
    assert intent.tool == "open_app"
    assert "youtube search for llm updates" in intent.args["app_name"]


def test_fastpath_open_browser_matches_open_app(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("open browser", origin="voice")
    assert intent is not None
    assert intent.tool == "open_app"
    assert intent.args["app_name"] == "browser"


def test_fastpath_multi_app_open_splits_to_shell_commands(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("open firefox and chrome", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.group == "app"
    assert intent.args["commands"] == ["firefox", "google-chrome"]


def test_fastpath_web_search_does_not_route_directly(orchestrator):
    intent = orchestrator._detect_direct_tool_intent(
        "search the web for latest ai news",
        origin="voice",
    )
    assert intent is None


def test_fastpath_open_downloads_matches_open_folder_shell(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("open downloads", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert "xdg-open" in intent.args["command"]
    assert "Downloads" in intent.args["command"]


def test_open_downloads_folder_uses_xdg_open(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("open downloads folder", origin="voice")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert "xdg-open" in intent.args["command"]
    assert "Downloads" in intent.args["command"]


def test_fastpath_open_downloads_with_comma_matches_folder(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("open downloads,", origin="voice")
    assert intent is not None
    assert intent.group == "app"


def test_take_screenshot_not_routed_as_fastpath(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("Take a screenshot.", origin="voice")
    assert intent is None


def test_fastpath_bye_not_routed_as_direct_tool(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("bye", origin="voice")
    assert intent is None


def test_fastpath_thanks_not_routed_as_direct_tool(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("thanks maya", origin="voice")
    assert intent is None


def test_fastpath_okay_not_routed_as_direct_tool(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("okay", origin="voice")
    assert intent is None


def test_fastpath_chat_origin_returns_deterministic(orchestrator):
    intent = orchestrator._detect_direct_tool_intent("change song", origin="chat")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.args["command"] == "playerctl next"
    assert intent.group == "media"


def test_fastpath_recall_question_excluded_from_direct_path(orchestrator):
    intent = orchestrator._detect_direct_tool_intent(
        "what did I ask you yesterday",
        origin="voice",
    )
    assert intent is None


def test_fastpath_recall_phrase_with_you_said_excluded(orchestrator):
    intent = orchestrator._detect_direct_tool_intent(
        "you said I should do this earlier",
        origin="voice",
    )
    assert intent is None


def test_extract_user_message_segment_from_bootstrap(orchestrator):
    query = "who is the prime minister of india"
    augmented = (
        "Conversation resume context:\n"
        "Conversation ID: abc123\n"
        "Recent tool results:\n"
        "- get_time: The time is 08:27 PM\n\n"
        "Current user message:\n"
        f"{query}"
    )
    assert orchestrator._extract_user_message_segment(augmented) == query


def test_extract_user_message_segment_returns_none_for_plain_message(orchestrator):
    assert orchestrator._extract_user_message_segment("hello there") is None


@pytest.mark.asyncio
async def test_fastpath_detection_uses_raw_user_segment_when_bootstrap_augmented(orchestrator):
    query = "who is the prime minister of india"
    augmented = (
        "Conversation resume context:\n"
        "Recent tool results:\n"
        "- get_time: The time is 08:27 PM\n\n"
        "Current user message:\n"
        f"{query}"
    )
    captured = {}

    def _capture_detect(message, origin="chat"):
        captured["message"] = message
        return None

    orchestrator._detect_direct_tool_intent = _capture_detect
    orchestrator._match_small_talk_fast_path = MagicMock(return_value="hello")

    await orchestrator._handle_chat_response(
        augmented,
        user_id="u1",
        origin="voice",
    )

    assert captured.get("message") == query


def test_factual_queries_not_get_time_after_segment_extraction(orchestrator):
    for query in FACTUAL_QUERIES:
        augmented = (
            "Conversation resume context:\n"
            "Recent tool results:\n"
            "- get_time: The time is 08:27 PM\n\n"
            "Current user message:\n"
            f"{query}"
        )
        extracted = orchestrator._extract_user_message_segment(augmented)
        assert extracted == query
        intent = orchestrator._detect_direct_tool_intent(extracted, origin="voice")
        assert intent is None or intent.tool != "get_time"


@pytest.mark.asyncio
async def test_fastpath_logs_planner_skipped_and_synthesis_skipped(orchestrator, caplog):
    orchestrator._execute_tool_call = AsyncMock(
        return_value=("Next track.", ToolInvocation(tool_name="run_shell_command", status="success"))
    )

    with caplog.at_level("INFO"):
        await orchestrator._handle_chat_response(
            "change song",
            user_id="u1",
            origin="voice",
        )

    assert "routing_mode=deterministic_fast_path" in caplog.text
    assert "planner_skipped=true" in caplog.text
    assert "synthesis_skipped=true" in caplog.text


@pytest.mark.asyncio
async def test_fastpath_voice_text_uses_template_not_synthesis(orchestrator):
    orchestrator._execute_tool_call = AsyncMock(
        return_value=({"status_message": "advanced output"}, ToolInvocation(tool_name="run_shell_command", status="success"))
    )
    orchestrator._synthesize_tool_response = AsyncMock(side_effect=AssertionError("should not be called"))

    response = await orchestrator._handle_chat_response(
        "change song",
        user_id="u1",
        origin="voice",
    )
    assert response.voice_text.startswith("Next track")


@pytest.mark.asyncio
async def test_fastpath_multi_app_executes_one_shell_call_per_app(orchestrator):
    orchestrator._execute_tool_call = AsyncMock(
        side_effect=[
            ("opened firefox", ToolInvocation(tool_name="run_shell_command", status="success")),
            ("opened chrome", ToolInvocation(tool_name="run_shell_command", status="success")),
        ]
    )

    response = await orchestrator._handle_chat_response(
        "open firefox and chrome",
        user_id="u1",
        origin="voice",
    )

    assert orchestrator._execute_tool_call.await_count == 2
    first_call = orchestrator._execute_tool_call.await_args_list[0].kwargs
    second_call = orchestrator._execute_tool_call.await_args_list[1].kwargs
    assert first_call["args"]["command"] == "firefox"
    assert second_call["args"]["command"] == "google-chrome"
    assert response.voice_text.lower().startswith("opening firefox and chrome")


@pytest.mark.asyncio
async def test_fastpath_time_response_includes_actual_time_value(orchestrator):
    orchestrator._execute_tool_call = AsyncMock(
        return_value=(
            {"success": True, "result": "The time is 12:28 PM"},
            ToolInvocation(tool_name="get_time", status="success"),
        )
    )

    response = await orchestrator._handle_chat_response(
        "what time is it",
        user_id="u1",
        origin="voice",
    )

    assert "12:28 PM" in response.voice_text
    assert response.voice_text.strip() != "Here's the current time."
