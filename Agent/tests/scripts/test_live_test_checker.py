from __future__ import annotations

from pathlib import Path

from scripts import live_test_checker as checker


def test_load_log_lines_auto_prefers_file(tmp_path: Path) -> None:
    log_file = tmp_path / "maya.log"
    log_file.write_text("line-a\nline-b\n", encoding="utf-8")

    source, lines = checker._load_log_lines(
        source="auto",
        max_lines=200,
        log_file=log_file,
        journal_unit=None,
    )

    assert source == "file"
    assert lines == ["line-a", "line-b"]


def test_load_log_lines_auto_falls_back_to_journal(tmp_path: Path, monkeypatch) -> None:
    log_file = tmp_path / "missing.log"

    monkeypatch.setattr(
        checker,
        "_read_journal",
        lambda max_lines, unit: ["journal-line-1", "journal-line-2"],
    )

    source, lines = checker._load_log_lines(
        source="auto",
        max_lines=100,
        log_file=log_file,
        journal_unit="maya.service",
    )

    assert source == "journal"
    assert lines == ["journal-line-1", "journal-line-2"]


def test_main_file_mode_missing_log_exits_usage(tmp_path: Path) -> None:
    missing = tmp_path / "none.log"
    code = checker.main(["--block", "1", "--source", "file", "--log-file", str(missing)])
    assert code == checker.EXIT_USAGE


def test_block1_pass_when_gate_present_and_no_tool_execution() -> None:
    lines = [
        "INFO conversational_tool_gate_applied origin=chat reason=small_talk_or_identity",
        "INFO identity_guardrail_applied reason=missing_maya_name",
    ]
    results = checker.evaluate_block(1, lines)
    required_passed, required_total = checker._count_required(results)

    assert required_passed == required_total


def test_block1_fail_when_tool_execution_leaks() -> None:
    lines = [
        "INFO conversational_tool_gate_applied origin=chat reason=small_talk_or_identity",
        "INFO CHAT path executing tool: web_search({'query':'x'})",
    ]
    results = checker.evaluate_block(1, lines)
    required_passed, required_total = checker._count_required(results)

    assert required_passed < required_total


def test_block2_pass_with_fast_path_tokens() -> None:
    lines = [
        "INFO routing_mode=deterministic_fast_path fast_path_group=time planner_skipped=true",
    ]
    results = checker.evaluate_block(2, lines)
    required_passed, required_total = checker._count_required(results)
    assert required_passed == required_total


def test_block3_fails_on_traceback_and_markup() -> None:
    lines = [
        "Traceback (most recent call last):",
        "<web_search>{\"query\":\"abc\"}</web_search>",
    ]
    results = checker.evaluate_block(3, lines)
    failed_required = [r for r in results if r.rule.required and not r.passed]
    assert failed_required


def test_block5_requires_voice_and_eou_tokens() -> None:
    lines_ok = [
        "INFO VOICE_TURN_ACCEPTED turn_id=abc seq=1 sender=user text=what time is it",
        "INFO turn_detection_active=eou_multilingual requested=eou",
    ]
    results_ok = checker.evaluate_block(5, lines_ok)
    ok_passed, ok_total = checker._count_required(results_ok)
    assert ok_passed == ok_total

    lines_fail = ["INFO VOICE_TURN_ACCEPTED turn_id=abc seq=1 sender=user text=hello"]
    results_fail = checker.evaluate_block(5, lines_fail)
    fail_passed, fail_total = checker._count_required(results_fail)
    assert fail_passed < fail_total


def test_block7_pass_and_fail_cases() -> None:
    pass_lines = [
        "INFO keyword_retrieval_skipped reason=sanitized_query_empty",
        "INFO tool_call_failed_safe_wrap tool_name=web_search error=timeout",
    ]
    pass_results = checker.evaluate_block(7, pass_lines)
    pass_required, pass_total = checker._count_required(pass_results)
    assert pass_required == pass_total

    fail_lines = [
        "ERROR FTS5 syntax error near MATCH",
        "INFO keyword_retrieval_skipped reason=sanitized_query_empty",
    ]
    fail_results = checker.evaluate_block(7, fail_lines)
    fail_required, fail_total = checker._count_required(fail_results)
    assert fail_required < fail_total


def test_block8_fails_on_tts_errors_and_passes_when_clean() -> None:
    fail_lines = [
        "ERROR:livekit.agents:Error in _tts_inference_task",
        "type='tts_error' error=APIConnectionError('could not connect')",
        "aiohttp.client_exceptions.WSServerHandshakeError: 403 invalid status",
    ]
    fail_results = checker.evaluate_block(8, fail_lines)
    fail_required, fail_total = checker._count_required(fail_results)
    assert fail_required < fail_total

    pass_lines = ["INFO tts_provider_active provider=elevenlabs model=default voice=xyz"]
    pass_results = checker.evaluate_block(8, pass_lines)
    pass_required, pass_total = checker._count_required(pass_results)
    assert pass_required == pass_total


def test_main_exit_code_pass_and_fail(tmp_path: Path) -> None:
    pass_file = tmp_path / "pass.log"
    pass_file.write_text(
        "INFO routing_mode=deterministic_fast_path fast_path_group=time\n",
        encoding="utf-8",
    )
    pass_code = checker.main(
        ["--block", "2", "--source", "file", "--log-file", str(pass_file), "--lines", "50"]
    )
    assert pass_code == checker.EXIT_OK

    fail_file = tmp_path / "fail.log"
    fail_file.write_text("INFO no fast path marker here\n", encoding="utf-8")
    fail_code = checker.main(
        ["--block", "2", "--source", "file", "--log-file", str(fail_file), "--lines", "50"]
    )
    assert fail_code == checker.EXIT_FAIL

