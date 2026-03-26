import tools


def test_tool_registry_exports_core_functions():
    expected_tools = [
        "get_weather",
        "search_web",
        "send_email",
        "set_alarm",
        "create_note",
        "create_calendar_event",
    ]

    for tool_name in expected_tools:
        assert hasattr(tools, tool_name), f"{tool_name} should be exposed by tools package"
        tool = getattr(tools, tool_name)
        assert callable(tool)


def test_tool_registry_all_contains_core_entries():
    assert "search_web" in tools.__all__
    assert "create_calendar_event" in tools.__all__
    assert tools.__all__ == list(dict.fromkeys(tools.__all__))
