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


def _collect_log_files(root: Path, explicit: list[str]) -> list[Path]:
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
    return files


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
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    thresholds = _load_thresholds((repo_root / args.threshold_config).resolve())
    log_files = _collect_log_files(repo_root, args.log)

    route_counter: Counter[str] = Counter()
    tts_fallback_count = 0
    tts_utterance_count = 0
    memory_write_failures = 0
    turn_latencies: list[float] = []
    bootstrap_ack_ms: list[float] = []
    bootstrap_events = 0

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
            for line in file_path.read_text(errors="ignore").splitlines():
                route = _extract_route(line)
                if route:
                    route_counter[route] += 1

                if any(marker in line for marker in tts_utterance_markers):
                    tts_utterance_count += 1
                if "tts_fallback_triggered" in line:
                    tts_fallback_count += 1
                if "memory_write_failed" in line:
                    memory_write_failures += 1

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
                "alert": bool(
                    turn_latency_p95 is not None
                    and turn_latency_p95 > float(thresholds["turn_latency_p95_max_ms"])
                ),
            },
            "bootstrap_ack_timing": {
                "datapoints": max(len(bootstrap_ack_ms), bootstrap_events),
                "events_seen": bootstrap_events,
                "p95_ms": bootstrap_ack_p95,
                "alert": bool(
                    bootstrap_ack_p95 is not None
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
