from typing import List

from core.orchestrator.fast_path_router import FastPathRouter


def _build_router(*, recall_exclusion: bool = False):
    turn_state = {}

    def parse_multi_app(app_phrase: str) -> List[str]:
        if app_phrase == "firefox and chrome":
            return ["firefox", "google-chrome"]
        return []

    def is_recall_exclusion_intent(_text: str) -> bool:
        return recall_exclusion

    router = FastPathRouter(
        turn_state=turn_state,
        parse_multi_app_fn=parse_multi_app,
        is_recall_exclusion_intent_fn=is_recall_exclusion_intent,
    )
    return router, turn_state


def test_time_query_returns_time_group():
    router, _ = _build_router()
    intent = router.detect_direct_tool_intent("what time is it", origin="voice")
    assert intent is not None
    assert intent.tool == "get_time"
    assert intent.group == "time"
    assert intent.template == "Here's the current time."


def test_date_query_returns_time_group():
    router, _ = _build_router()
    intent = router.detect_direct_tool_intent("what's the date", origin="chat")
    assert intent is not None
    assert intent.tool == "get_date"
    assert intent.group == "time"
    assert intent.template == "Here's today's date."


def test_note_intents_preserve_shape():
    router, _ = _build_router()

    created = router.detect_direct_tool_intent("create note trip ideas with content book tickets", origin="chat")
    assert created is not None
    assert created.tool == "create_note"
    assert created.args == {"title": "trip ideas", "content": "book tickets"}
    assert created.group == "notes"

    read = router.detect_direct_tool_intent("read note trip ideas", origin="chat")
    assert read is not None
    assert read.tool == "read_note"
    assert read.args == {"title": "trip ideas"}
    assert read.group == "notes"

    deleted = router.detect_direct_tool_intent("delete note trip ideas", origin="chat")
    assert deleted is not None
    assert deleted.tool == "delete_note"
    assert deleted.args == {"title": "trip ideas"}
    assert deleted.group == "notes"

    listed = router.detect_direct_tool_intent("list notes", origin="chat")
    assert listed is not None
    assert listed.tool == "list_notes"
    assert listed.args == {}
    assert listed.group == "notes"


def test_media_controls_preserve_exact_mappings():
    router, _ = _build_router()

    assert router.detect_direct_tool_intent("next track").args["command"] == "playerctl next"
    assert router.detect_direct_tool_intent("previous song").args["command"] == "playerctl previous"
    assert router.detect_direct_tool_intent("pause music").args["command"] == "playerctl pause"
    assert router.detect_direct_tool_intent("resume music").args["command"] == "playerctl play"
    assert router.detect_direct_tool_intent("stop playback").args["command"] == "playerctl stop"
    assert router.detect_direct_tool_intent("volume up").args["command"] == "playerctl volume 0.1+"
    assert router.detect_direct_tool_intent("volume down").args["command"] == "playerctl volume 0.1-"
    assert router.detect_direct_tool_intent("mute").args["command"] == "playerctl volume 0.0"

    set_volume = router.detect_direct_tool_intent("set volume to 42%")
    assert set_volume is not None
    assert set_volume.tool == "set_volume"
    assert set_volume.args == {"percent": 42}
    assert set_volume.group == "media"


def test_youtube_open_and_search_preserve_turn_state():
    router, turn_state = _build_router()

    opened = router.detect_direct_tool_intent("open youtube")
    assert opened is not None
    assert opened.tool == "open_app"
    assert opened.args == {"app_name": "youtube"}
    assert opened.group == "youtube"
    assert turn_state["last_search_target"] == "youtube"

    searched = router.detect_direct_tool_intent("search youtube for llm updates")
    assert searched is not None
    assert searched.tool == "open_app"
    assert searched.args == {"app_name": "youtube search for llm updates"}
    assert searched.group == "youtube"
    assert turn_state["last_search_target"] == "youtube"
    assert turn_state["last_search_query"] == "llm updates"


def test_folder_open_returns_xdg_open_command():
    router, _ = _build_router()
    intent = router.detect_direct_tool_intent("open downloads folder")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert "xdg-open" in intent.args["command"]
    assert "Downloads" in intent.args["command"]
    assert intent.group == "app"


def test_multi_app_open_uses_injected_parser():
    router, _ = _build_router()
    intent = router.detect_direct_tool_intent("open firefox and chrome")
    assert intent is not None
    assert intent.tool == "run_shell_command"
    assert intent.args == {"commands": ["firefox", "google-chrome"]}
    assert intent.group == "app"


def test_open_and_close_app_preserve_app_group():
    router, _ = _build_router()

    opened = router.detect_direct_tool_intent("open browser")
    assert opened is not None
    assert opened.tool == "open_app"
    assert opened.args == {"app_name": "browser"}
    assert opened.group == "app"

    closed = router.detect_direct_tool_intent("close firefox")
    assert closed is not None
    assert closed.tool == "close_app"
    assert closed.args == {"app_name": "firefox"}
    assert closed.group == "app"


def test_recall_exclusion_returns_none():
    router, _ = _build_router(recall_exclusion=True)
    assert router.detect_direct_tool_intent("what did I ask you yesterday", origin="voice") is None


def test_factual_non_time_query_does_not_match_time():
    router, _ = _build_router()
    intent = router.detect_direct_tool_intent("who is the CEO of OpenAI", origin="voice")
    assert intent is None or intent.tool != "get_time"
