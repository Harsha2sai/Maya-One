from core.response.response_formatter import ResponseFormatter


def test_extract_display_candidate_web_search_returns_snippet():
    structured = {
        "results": [
            {"title": "A", "snippet": "Latest AI updates from trusted sources."}
        ]
    }
    result = ResponseFormatter.extract_display_candidate(structured, "web_search")
    assert result == "Latest AI updates from trusted sources."


def test_extract_display_candidate_open_app_returns_formatted_string():
    structured = {"app_name": "youtube"}
    result = ResponseFormatter.extract_display_candidate(structured, "open_app")
    assert result == "Opened youtube."


def test_extract_display_candidate_unknown_tool_returns_none():
    structured = {"summary": "something useful"}
    result = ResponseFormatter.extract_display_candidate(structured, "unknown_tool")
    assert result is None


def test_extract_display_candidate_never_returns_raw_dict_string():
    structured = {"summary": '{"status":"ok","value":123}'}
    result = ResponseFormatter.extract_display_candidate(structured, "get_weather")
    assert result is None


def test_extract_display_candidate_truncates_to_200_chars():
    long_text = "word " * 80
    structured = {"summary": long_text}
    result = ResponseFormatter.extract_display_candidate(structured, "get_weather")
    assert result is not None
    assert len(result) <= 200


def test_voice_brief_strips_markdown_bold():
    text = "**Important** update available."
    result = ResponseFormatter.to_voice_brief(text, intent_type="informational")
    assert "**" not in result
    assert "Important update available." in result


def test_voice_brief_strips_code_blocks():
    text = "Use this:\n```python\nprint('x')\n```\nDone now."
    result = ResponseFormatter.to_voice_brief(text, intent_type="informational")
    assert "print('x')" not in result
    assert "Done now." in result


def test_voice_brief_strips_urls():
    text = "Read more at https://example.com/docs now."
    result = ResponseFormatter.to_voice_brief(text, intent_type="informational")
    assert "http" not in result.lower()


def test_voice_brief_strips_list_markers():
    text = "- one\n- two\n- three"
    result = ResponseFormatter.to_voice_brief(text, intent_type="informational")
    assert "-" not in result


def test_voice_brief_direct_action_caps_at_1_sentence():
    text = "Done first. Done second. Done third."
    result = ResponseFormatter.to_voice_brief(
        text,
        intent_type="direct_action",
        max_sentences_direct=1,
    )
    assert result.count(".") <= 1
    assert "Done second" not in result


def test_voice_brief_informational_caps_at_2_sentences():
    text = "First sentence. Second sentence. Third sentence."
    result = ResponseFormatter.to_voice_brief(
        text,
        intent_type="informational",
        max_sentences_info=2,
    )
    assert "Third sentence" not in result


def test_voice_brief_char_cap_does_not_cut_mid_word():
    text = "This sentence should stop before a halfword appears in output."
    result = ResponseFormatter.to_voice_brief(
        text,
        intent_type="direct_action",
        max_chars_direct=24,
    )
    assert not result.endswith("hal")
    assert result.endswith(".")


def test_voice_brief_char_cap_direct_140():
    text = "word " * 80
    result = ResponseFormatter.to_voice_brief(
        text,
        intent_type="direct_action",
        max_chars_direct=140,
    )
    assert len(result) <= 141


def test_voice_brief_char_cap_info_300():
    text = "word " * 120
    result = ResponseFormatter.to_voice_brief(
        text,
        intent_type="informational",
        max_chars_info=300,
    )
    assert len(result) <= 301


def test_voice_brief_empty_input_returns_done():
    result = ResponseFormatter.to_voice_brief("", intent_type="informational")
    assert result == "Done."


def test_voice_brief_fast_path_returns_unchanged():
    text = "Next track."
    result = ResponseFormatter.to_voice_brief(text, intent_type="fast_path")
    assert result == text


def test_voice_brief_already_short_returns_unchanged():
    text = "Opening YouTube."
    result = ResponseFormatter.to_voice_brief(text, intent_type="direct_action")
    assert result == text


def test_voice_brief_only_urls_returns_done():
    text = "https://example.com www.example.org"
    result = ResponseFormatter.to_voice_brief(text, intent_type="informational")
    assert result == "Done."


def test_voice_brief_multiline_collapses_whitespace():
    text = "Line one.\n\nLine two.\t\tLine three."
    result = ResponseFormatter.to_voice_brief(
        text,
        intent_type="informational",
        max_sentences_info=2,
    )
    assert "\n" not in result
    assert "  " not in result


def test_normalize_response_parses_json_prefixed_with_json_and_trailing_text():
    raw = (
        'json {"display_text":"Your alarm has been set for 7AM tomorrow.",'
        '"voice_text":"Your alarm is set for tomorrow at 7AM.",'
        '"confidence":1.0,"mode":"text"} [1] This is a reference...'
    )

    result = ResponseFormatter.normalize_response(raw)

    assert result.display_text == "Your alarm has been set for 7AM tomorrow."
    assert result.voice_text == "Your alarm is set for tomorrow at 7AM."
    assert "json {" not in result.display_text
