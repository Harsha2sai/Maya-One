#!/usr/bin/env python3
"""Fail-fast gate for monitoring bootstrap reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_report(path: Path) -> dict:
    loaded = json.loads(path.read_text())
    if not isinstance(loaded, dict):
        raise ValueError("report must be a JSON object")
    return loaded


def _evaluate_metrics(report: dict, strict: bool) -> tuple[list[str], list[str]]:
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        return ["report.metrics missing or invalid"], []

    failures: list[str] = []
    warnings: list[str] = []

    for metric_name, payload in metrics.items():
        if not isinstance(payload, dict):
            warnings.append(f"{metric_name}: payload invalid")
            continue

        datapoints = int(payload.get("datapoints", 0) or 0)
        alert = bool(payload.get("alert", False))

        if alert:
            failures.append(f"{metric_name}: alert=true")
        elif strict and datapoints == 0:
            failures.append(f"{metric_name}: datapoints=0 in --strict mode")
        elif datapoints == 0:
            warnings.append(f"{metric_name}: datapoints=0")

    return failures, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate monitoring bootstrap report.")
    parser.add_argument(
        "--report",
        default="reports/monitoring_bootstrap.json",
        help="Path to monitoring bootstrap JSON report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any metric has zero datapoints.",
    )
    args = parser.parse_args()

    report_path = Path(args.report).expanduser().resolve()
    if not report_path.exists():
        print(f"monitoring_gate_fail report_not_found={report_path}")
        return 2

    try:
        report = _load_report(report_path)
    except Exception as exc:
        print(f"monitoring_gate_fail report_invalid={report_path} error={exc}")
        return 2

    failures, warnings = _evaluate_metrics(report, strict=bool(args.strict))

    print(f"monitoring_gate_report={report_path}")
    for warning in warnings:
        print(f"warning: {warning}")
    if failures:
        for failure in failures:
            print(f"fail: {failure}")
        print("monitoring_gate_status=FAIL")
        return 1

    print("monitoring_gate_status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
