#!/usr/bin/env python3
"""
Block-based log checker for live Flutter + backend test runs.

This script validates expected/forbidden log signals after each manual test block.
It does not simulate user input; it only inspects recent backend logs.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


@dataclass(frozen=True)
class CheckRule:
    name: str
    kind: str  # must_contain | must_not_contain
    pattern: str
    required: bool = True


@dataclass
class CheckResult:
    rule: CheckRule
    passed: bool
    evidence: str


BLOCK_RULES: dict[int, list[CheckRule]] = {
    1: [
        CheckRule(
            name="conversation_or_identity_gate_present",
            kind="must_contain",
            pattern=r"conversational_tool_gate_applied|identity_guardrail_applied",
        ),
        CheckRule(
            name="no_chat_tool_execution_log",
            kind="must_not_contain",
            pattern=r"CHAT path executing tool",
        ),
        CheckRule(
            name="no_tool_executed_marker",
            kind="must_not_contain",
            pattern=r"tool_executed=",
        ),
        CheckRule(
            name="no_shell_command_execution_marker",
            kind="must_not_contain",
            pattern=r"run_shell_command\(",
        ),
    ],
    2: [
        CheckRule(
            name="deterministic_fast_path_used",
            kind="must_contain",
            pattern=r"routing_mode=deterministic_fast_path",
        ),
        CheckRule(
            name="fast_path_group_logged",
            kind="must_contain",
            pattern=r"fast_path_group=",
        ),
    ],
    3: [
        CheckRule(
            name="no_traceback",
            kind="must_not_contain",
            pattern=r"Traceback",
        ),
        CheckRule(
            name="no_tool_markup_leak",
            kind="must_not_contain",
            pattern=r"tool_markup_leak_detected",
        ),
        CheckRule(
            name="no_raw_tool_markup_xml",
            kind="must_not_contain",
            pattern=r"<[a-z_]+>\{.*\}</[a-z_]+>",
        ),
        CheckRule(
            name="no_raw_traceback_error_text",
            kind="must_not_contain",
            pattern=r"error executing command: Traceback",
        ),
    ],
    5: [
        CheckRule(
            name="voice_turn_accepted_present",
            kind="must_contain",
            pattern=r"VOICE_TURN_ACCEPTED",
        ),
        CheckRule(
            name="eou_or_turn_detection_present",
            kind="must_contain",
            pattern=r"turn_detection_active=eou|turn_detection_active=eou_multilingual|turn_detect|eou",
        ),
    ],
    7: [
        CheckRule(
            name="fts_sanitization_signal_present",
            kind="must_contain",
            pattern=r"keyword_retrieval_skipped reason=sanitized_query_empty|sanitize_fts_query",
        ),
        CheckRule(
            name="no_fts_syntax_error",
            kind="must_not_contain",
            pattern=r"FTS5.*syntax|syntax error.*MATCH",
        ),
        CheckRule(
            name="no_traceback",
            kind="must_not_contain",
            pattern=r"Traceback",
        ),
        CheckRule(
            name="safe_wrap_observed_optional",
            kind="must_contain",
            pattern=r"tool_call_failed_safe_wrap",
            required=False,
        ),
    ],
    8: [
        CheckRule(
            name="no_tts_inference_task_error",
            kind="must_not_contain",
            pattern=r"_tts_inference_task",
        ),
        CheckRule(
            name="no_tts_error_event",
            kind="must_not_contain",
            pattern=r"tts_error",
        ),
        CheckRule(
            name="no_http_401_403",
            kind="must_not_contain",
            pattern=r"\b401\b|\b403\b",
        ),
        CheckRule(
            name="no_error_in_tts_inference_task",
            kind="must_not_contain",
            pattern=r"Error in _tts_inference_task",
        ),
    ],
}


def _tail_file(path: Path, max_lines: int) -> list[str]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return list(deque((line.rstrip("\n") for line in fh), maxlen=max_lines))


def _read_journal(max_lines: int, unit: str | None) -> list[str]:
    cmd = ["journalctl"]
    if unit:
        cmd.extend(["-u", unit])
    cmd.extend(["-n", str(max_lines), "--no-pager", "-o", "cat"])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("journalctl is not available on this system") from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"journalctl failed: {err or 'unknown error'}")

    return [line.rstrip("\n") for line in proc.stdout.splitlines()]


def _load_log_lines(
    source: str,
    max_lines: int,
    log_file: Path,
    journal_unit: str | None,
) -> tuple[str, list[str]]:
    if source == "file":
        if not log_file.exists() or log_file.stat().st_size == 0:
            raise RuntimeError(f"log file is missing or empty: {log_file}")
        return "file", _tail_file(log_file, max_lines)

    if source == "journal":
        return "journal", _read_journal(max_lines, journal_unit)

    # source=auto
    if log_file.exists() and log_file.stat().st_size > 0:
        return "file", _tail_file(log_file, max_lines)

    return "journal", _read_journal(max_lines, journal_unit)


def _first_match(lines: Sequence[str], regex: re.Pattern[str]) -> str | None:
    for line in lines:
        if regex.search(line):
            return line
    return None


def evaluate_block(block: int, lines: Sequence[str]) -> list[CheckResult]:
    rules = BLOCK_RULES[block]
    results: list[CheckResult] = []
    for rule in rules:
        regex = re.compile(rule.pattern, re.IGNORECASE)
        match_line = _first_match(lines, regex)
        if rule.kind == "must_contain":
            if match_line:
                results.append(CheckResult(rule=rule, passed=True, evidence=match_line))
            elif rule.required:
                results.append(
                    CheckResult(
                        rule=rule,
                        passed=False,
                        evidence=f"missing pattern: /{rule.pattern}/",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        rule=rule,
                        passed=True,
                        evidence=f"optional signal not observed: /{rule.pattern}/",
                    )
                )
            continue

        # must_not_contain
        if match_line:
            results.append(CheckResult(rule=rule, passed=False, evidence=match_line))
        else:
            results.append(
                CheckResult(
                    rule=rule,
                    passed=True,
                    evidence=f"no matches for /{rule.pattern}/",
                )
            )
    return results


def _format_result_line(result: CheckResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    return f"[{status}] {result.rule.name} :: {result.evidence}"


def _count_required(results: Iterable[CheckResult]) -> tuple[int, int]:
    required = [r for r in results if r.rule.required]
    passed = [r for r in required if r.passed]
    return len(passed), len(required)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate live Flutter/backend log signals for a given test block.",
    )
    parser.add_argument(
        "--block",
        type=int,
        required=True,
        choices=sorted(BLOCK_RULES.keys()),
        help="Block number to validate: 1, 2, 3, 5, 7, or 8",
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=200,
        help="Number of most recent lines to scan",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "file", "journal"),
        default="auto",
        help="Log source selection mode",
    )
    parser.add_argument(
        "--log-file",
        default="/tmp/maya_flutter_tts.log",
        help="Log file path when using file or auto source mode",
    )
    parser.add_argument(
        "--journal-unit",
        default="",
        help="Optional systemd unit name for journal source mode",
    )
    parser.add_argument(
        "--print-scan-source",
        action="store_true",
        help="Print the resolved scan source (file/journal)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    lines_to_scan = max(1, args.lines)
    log_file = Path(args.log_file)
    journal_unit = args.journal_unit.strip() or None

    try:
        resolved_source, lines = _load_log_lines(
            source=args.source,
            max_lines=lines_to_scan,
            log_file=log_file,
            journal_unit=journal_unit,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.print_scan_source:
        print(f"Scan source: {resolved_source}")

    print(f"Block: {args.block}")
    print(f"Source: {resolved_source}")
    print(f"Lines scanned: {len(lines)}")

    results = evaluate_block(args.block, lines)
    for result in results:
        print(_format_result_line(result))

    passed_required, total_required = _count_required(results)
    all_required_passed = passed_required == total_required
    print(f"Result: {'PASS' if all_required_passed else 'FAIL'}")
    print(f"Passed checks: {passed_required}/{total_required}")

    return EXIT_OK if all_required_passed else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())

