#!/usr/bin/env python3
"""
Bootstrap monitoring metrics from existing Maya logs.

Produces a lightweight JSON snapshot for:
- route distribution
- TTS fallback rate
- memory write failures
- turn latency p95
- bootstrap ack timing
"""

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_THRESHOLDS = {
    "route_get_time_max_ratio_10m": 0.2,
    "tts_fallback_rate_max_ratio": 0.1,
    "memory_write_failed_max_5m": 0,
    "turn_latency_p95_max_ms": 3000,
    "bootstrap_ack_max_ms": 2000,
    "fact_classifier_fallback_rate_max_ratio": 0.2,
    "shadow_router_invalid_max_ratio": 0.1,
    "shadow_router_agreement_min_ratio": 0.85,
    "pronoun_clarification_fallback_max_ratio": 0.05,
}


def _load_thresholds(config_path: Path | None) -> dict[str, Any]:
    if config_path and config_path.exists():
        try:
            loaded = json.loads(config_path.read_text())
            if isinstance(loaded, dict):
                return {**DEFAULT_THRESHOLDS, **loaded}
        except Exception:
            pass
    return dict(DEFAULT_THRESHOLDS)


def _collect_log_files(root: Path, explicit: list[str], recent_files: int | None = None) -> list[Path]:
    if explicit:
        paths = [Path(p).expanduser() for p in explicit]
        return [p for p in paths if p.exists() and p.is_file()]

    candidates = [
        root / "logs" / "audit.log",
        *sorted((root / "logs").glob("*.log")),
        *sorted((root / "logs" / "sessions").glob("*.log")),
    ]
    seen: set[Path] = set()
    files: list[Path] = []
    for file_path in candidates:
        if file_path.exists() and file_path.is_file() and file_path not in seen:
            seen.add(file_path)
            files.append(file_path)
    if recent_files and recent_files > 0:
        files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:recent_files]
        files = sorted(files, key=lambda p: p.stat().st_mtime)
    return files


def _tail_lines(file_path: Path, max_lines_per_file: int) -> list[str]:
    try:
        lines = file_path.read_text(errors="ignore").splitlines()
    except Exception:
        return []
    if max_lines_per_file > 0 and len(lines) > max_lines_per_file:
        return lines[-max_lines_per_file:]
    return lines


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return ordered[idx]


def _extract_route(line: str) -> str | None:
    mode_match = re.search(r"routing_mode=([a-zA-Z0-9_:-]+)", line)
    if mode_match:
        return mode_match.group(1).lower()
    router_match = re.search(r"agent_router_decision: .*->\s*([a-zA-Z0-9_:-]+)", line)
    if router_match:
        return router_match.group(1).lower()
    return None


def _parse_shadow_router(line: str) -> tuple[str, str, str | None] | None:
    match = re.search(
        r"agent_router_shadow legacy=([a-zA-Z0-9_:-]+)\s+state=([a-zA-Z0-9_:-]+)\s+action=(\{.*\})",
        line,
    )
    if not match:
        return None
    legacy_route = match.group(1).lower()
    state = match.group(2).lower()
    action_type = None
    try:
        action = json.loads(match.group(3))
        raw_type = str(action.get("type") or "").strip().lower()
        action_type = raw_type or None
    except Exception:
        action_type = None
    return legacy_route, state, action_type


def main() -> int:
    parser = argparse.ArgumentParser(description="Build initial monitoring snapshot from logs.")
    parser.add_argument("--log", action="append", default=[], help="Explicit log file path (repeatable).")
    parser.add_argument(
        "--threshold-config",
        default="config/monitoring_thresholds.json",
        help="Path to threshold JSON config.",
    )
    parser.add_argument(
        "--output",
        default="reports/monitoring_bootstrap.json",
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--recent-files",
        type=int,
        default=5,
        help="How many most-recent log files to scan when --log is not set (default: 5).",
    )
    parser.add_argument(
        "--max-lines-per-file",
        type=int,
        default=4000,
        help="Tail this many lines per file to avoid lifetime aggregate bias (default: 4000).",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    thresholds = _load_thresholds((repo_root / args.threshold_config).resolve())
    log_files = _collect_log_files(repo_root, args.log, recent_files=args.recent_files)

    route_counter: Counter[str] = Counter()
    tts_fallback_count = 0
    tts_utterance_count = 0
    memory_write_failures = 0
    turn_latencies: list[float] = []
    bootstrap_ack_ms: list[float] = []
    bootstrap_events = 0
    fact_classifier_attempts = 0
    fact_classifier_failures = 0
    shadow_events_total = 0
    shadow_events_invalid = 0
    shadow_events_valid = 0
    shadow_agreement_hits = 0
    pronoun_rewrite_events = 0
    pronoun_clarification_fallbacks = 0

    turn_latency_re = re.compile(r"TURN_TIMING[^\n]*total_ms=([0-9]+(?:\.[0-9]+)?)")
    ack_timing_re = re.compile(r"bootstrap_ack_timing_ms=([0-9]+(?:\.[0-9]+)?)")
    tts_utterance_markers = (
        "tts_synthesis_start",
        "tts_voice_summary:",
        "greeting_sent provider=",
        "greeting_sent_via_fallback",
    )
    bootstrap_event_markers = (
        "bootstrap_context_applied",
        "bootstrap_acknowledged",
        "bootstrap_timeout",
        "bootstrap_started",
        "bootstrap_context_received",
    )

    for file_path in log_files:
        try:
            for line in _tail_lines(file_path, args.max_lines_per_file):
                route = _extract_route(line)
                if route:
                    route_counter[route] += 1

                if any(marker in line for marker in tts_utterance_markers):
                    tts_utterance_count += 1
                if "tts_fallback_triggered" in line:
                    tts_fallback_count += 1
                if "memory_write_failed" in line:
                    memory_write_failures += 1
                if "fact_classifier result=" in line:
                    fact_classifier_attempts += 1
                if "fact_classifier_failed" in line:
                    fact_classifier_attempts += 1
                    fact_classifier_failures += 1

                shadow_parsed = _parse_shadow_router(line)
                if shadow_parsed:
                    legacy_route, shadow_state, shadow_type = shadow_parsed
                    shadow_events_total += 1
                    if shadow_state == "shadow-invalid":
                        shadow_events_invalid += 1
                    else:
                        shadow_events_valid += 1
                        if shadow_type == legacy_route:
                            shadow_agreement_hits += 1

                if "research_pronoun_override" in line:
                    pronoun_rewrite_events += 1
                    if "forced=false" in line and "ambiguous=true" in line:
                        pronoun_clarification_fallbacks += 1

                turn_match = turn_latency_re.search(line)
                if turn_match:
                    turn_latencies.append(float(turn_match.group(1)))

                ack_match = ack_timing_re.search(line)
                if ack_match:
                    bootstrap_ack_ms.append(float(ack_match.group(1)))
                if any(marker in line for marker in bootstrap_event_markers):
                    bootstrap_events += 1
        except Exception:
            continue

    total_routes = sum(route_counter.values())
    get_time_ratio = (
        (route_counter.get("get_time", 0) / total_routes) if total_routes > 0 else None
    )
    tts_fallback_ratio = (
        (tts_fallback_count / tts_utterance_count) if tts_utterance_count > 0 else None
    )
    fact_classifier_fallback_ratio = (
        (fact_classifier_failures / fact_classifier_attempts)
        if fact_classifier_attempts > 0
        else None
    )
    shadow_invalid_ratio = (
        (shadow_events_invalid / shadow_events_total) if shadow_events_total > 0 else None
    )
    shadow_agreement_ratio = (
        (shadow_agreement_hits / shadow_events_valid) if shadow_events_valid > 0 else None
    )
    pronoun_clarification_fallback_ratio = (
        (pronoun_clarification_fallbacks / pronoun_rewrite_events)
        if pronoun_rewrite_events > 0
        else None
    )
    turn_latency_p95 = _p95(turn_latencies)
    bootstrap_ack_p95 = _p95(bootstrap_ack_ms)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": [str(p) for p in log_files],
        "thresholds": thresholds,
        "metrics": {
            "route_distribution": {
                "datapoints": total_routes,
                "counts": dict(route_counter),
                "get_time_ratio": get_time_ratio,
                "alert": bool(
                    get_time_ratio is not None
                    and get_time_ratio > float(thresholds["route_get_time_max_ratio_10m"])
                ),
            },
            "tts_fallback_rate": {
                "datapoints": tts_utterance_count,
                "fallback_events": tts_fallback_count,
                "ratio": tts_fallback_ratio,
                "alert": bool(
                    tts_fallback_ratio is not None
                    and tts_fallback_ratio > float(thresholds["tts_fallback_rate_max_ratio"])
                ),
            },
            "memory_write_failures": {
                "datapoints": memory_write_failures,
                "count": memory_write_failures,
                "alert": memory_write_failures > int(thresholds["memory_write_failed_max_5m"]),
            },
            "turn_latency_p95": {
                "datapoints": len(turn_latencies),
                "p95_ms": turn_latency_p95,
                "min_datapoints_for_alert": 5,
                "alert": bool(
                    len(turn_latencies) >= 5
                    and turn_latency_p95 is not None
                    and turn_latency_p95 > float(thresholds["turn_latency_p95_max_ms"])
                ),
            },
            "fact_classifier_fallback_rate": {
                "datapoints": fact_classifier_attempts,
                "failures": fact_classifier_failures,
                "ratio": fact_classifier_fallback_ratio,
                "min_datapoints_for_alert": 5,
                "alert": bool(
                    fact_classifier_attempts >= 5
                    and fact_classifier_fallback_ratio is not None
                    and fact_classifier_fallback_ratio
                    > float(thresholds["fact_classifier_fallback_rate_max_ratio"])
                ),
            },
            "shadow_router_invalid_rate": {
                "datapoints": shadow_events_total,
                "invalid_events": shadow_events_invalid,
                "ratio": shadow_invalid_ratio,
                "min_datapoints_for_alert": 5,
                "alert": bool(
                    shadow_events_total >= 5
                    and shadow_invalid_ratio is not None
                    and shadow_invalid_ratio > float(thresholds["shadow_router_invalid_max_ratio"])
                ),
            },
            "shadow_router_agreement_rate": {
                "datapoints": shadow_events_valid,
                "agreements": shadow_agreement_hits,
                "ratio": shadow_agreement_ratio,
                "min_datapoints_for_alert": 5,
                "alert": bool(
                    shadow_events_valid >= 5
                    and shadow_agreement_ratio is not None
                    and shadow_agreement_ratio < float(thresholds["shadow_router_agreement_min_ratio"])
                ),
            },
            "pronoun_clarification_fallback_rate": {
                "datapoints": pronoun_rewrite_events,
                "fallbacks": pronoun_clarification_fallbacks,
                "ratio": pronoun_clarification_fallback_ratio,
                "min_datapoints_for_alert": 5,
                "alert": bool(
                    pronoun_rewrite_events >= 5
                    and pronoun_clarification_fallback_ratio is not None
                    and pronoun_clarification_fallback_ratio
                    > float(thresholds["pronoun_clarification_fallback_max_ratio"])
                ),
            },
            "bootstrap_ack_timing": {
                "datapoints": max(len(bootstrap_ack_ms), bootstrap_events),
                "events_seen": bootstrap_events,
                "p95_ms": bootstrap_ack_p95,
                "min_datapoints_for_alert": 5,
                "alert": bool(
                    len(bootstrap_ack_ms) >= 5
                    and bootstrap_ack_p95 is not None
                    and bootstrap_ack_p95 > float(thresholds["bootstrap_ack_max_ms"])
                ),
            },
        },
    }

    output_path = (repo_root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"monitoring_bootstrap_report={output_path}")
    for metric_name, payload in report["metrics"].items():
        print(f"{metric_name}: datapoints={payload.get('datapoints', 0)} alert={payload.get('alert', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
