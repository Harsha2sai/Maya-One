from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _bootstrap_script() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "monitoring_bootstrap.py"


def _gate_script() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "monitoring_gate.py"


def test_monitoring_bootstrap_extracts_hardening_metrics(tmp_path: Path) -> None:
    log_path = tmp_path / "maya.log"
    report_path = tmp_path / "monitoring.json"

    log_lines = [
        "agent_router_decision: 'what time' -> get_time",
        "agent_router_decision: 'hello' -> chat",
        "TURN_TIMING total_ms=120",
        "TURN_TIMING total_ms=180",
        "bootstrap_ack_timing_ms=900",
        "bootstrap_context_applied",
        "tts_synthesis_start",
        "tts_voice_summary:",
        "tts_fallback_triggered",
        "fact_classifier result=fact message='a'",
        "fact_classifier result=research message='b'",
        "fact_classifier result=fact message='c'",
        "fact_classifier_failed error=timeout",
        "fact_classifier_failed error=timeout-2",
        "agent_router_shadow legacy=research state=valid action={\"type\":\"research\",\"target\":\"research\",\"tool\":null,\"arguments\":{},\"confidence\":0.9,\"reason\":\"ok\"}",
        "agent_router_shadow legacy=chat state=valid action={\"type\":\"chat\",\"target\":\"chat\",\"tool\":null,\"arguments\":{},\"confidence\":0.9,\"reason\":\"ok\"}",
        "agent_router_shadow legacy=system state=valid action={\"type\":\"chat\",\"target\":\"chat\",\"tool\":null,\"arguments\":{},\"confidence\":0.9,\"reason\":\"mismatch\"}",
        "agent_router_shadow legacy=research state=valid action={\"type\":\"chat\",\"target\":\"chat\",\"tool\":null,\"arguments\":{},\"confidence\":0.8,\"reason\":\"mismatch\"}",
        "agent_router_shadow legacy=identity state=valid action={\"type\":\"chat\",\"target\":\"chat\",\"tool\":null,\"arguments\":{},\"confidence\":0.8,\"reason\":\"mismatch\"}",
        "agent_router_shadow legacy=research state=shadow-invalid action={\"type\":\"research\",\"target\":\"research\",\"tool\":null,\"arguments\":{},\"confidence\":0.1,\"reason\":\"invalid\"}",
        "research_pronoun_override forced=true ambiguous=false rewritten=Tell me more about PM",
        "research_pronoun_override forced=true ambiguous=false rewritten=Tell me more",
        "research_pronoun_override forced=true ambiguous=false rewritten=Give details",
        "research_pronoun_override forced=true ambiguous=false rewritten=Explain this",
        "research_pronoun_override forced=false ambiguous=true rewritten=tell me more about him",
    ]
    log_path.write_text("\n".join(log_lines), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(_bootstrap_script()),
            "--log",
            str(log_path),
            "--output",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    metrics = payload["metrics"]

    assert metrics["fact_classifier_fallback_rate"]["datapoints"] == 5
    assert metrics["fact_classifier_fallback_rate"]["failures"] == 2
    assert metrics["fact_classifier_fallback_rate"]["ratio"] == 0.4
    assert metrics["fact_classifier_fallback_rate"]["alert"] is True

    assert metrics["shadow_router_invalid_rate"]["datapoints"] == 6
    assert metrics["shadow_router_invalid_rate"]["invalid_events"] == 1
    assert round(metrics["shadow_router_invalid_rate"]["ratio"], 4) == round(1 / 6, 4)
    assert metrics["shadow_router_invalid_rate"]["alert"] is True

    assert metrics["shadow_router_agreement_rate"]["datapoints"] == 5
    assert metrics["shadow_router_agreement_rate"]["agreements"] == 2
    assert round(metrics["shadow_router_agreement_rate"]["ratio"], 4) == round(2 / 5, 4)
    assert metrics["shadow_router_agreement_rate"]["alert"] is True

    assert metrics["pronoun_clarification_fallback_rate"]["datapoints"] == 5
    assert metrics["pronoun_clarification_fallback_rate"]["fallbacks"] == 1
    assert metrics["pronoun_clarification_fallback_rate"]["ratio"] == 0.2
    assert metrics["pronoun_clarification_fallback_rate"]["alert"] is True


def test_monitoring_gate_pass_and_fail_modes(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"

    report_path.write_text(
        json.dumps(
            {
                "metrics": {
                    "good_metric": {"datapoints": 2, "alert": False},
                    "zero_data_metric": {"datapoints": 0, "alert": False},
                }
            }
        ),
        encoding="utf-8",
    )

    relaxed = subprocess.run(
        [sys.executable, str(_gate_script()), "--report", str(report_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert relaxed.returncode == 0, relaxed.stdout + relaxed.stderr
    assert "monitoring_gate_status=PASS" in relaxed.stdout

    strict = subprocess.run(
        [sys.executable, str(_gate_script()), "--report", str(report_path), "--strict"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert strict.returncode == 1, strict.stdout + strict.stderr
    assert "zero_data_metric" in strict.stdout
    assert "monitoring_gate_status=FAIL" in strict.stdout

    report_path.write_text(
        json.dumps({"metrics": {"bad_metric": {"datapoints": 5, "alert": True}}}),
        encoding="utf-8",
    )
    alert_fail = subprocess.run(
        [sys.executable, str(_gate_script()), "--report", str(report_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert alert_fail.returncode == 1
    assert "bad_metric" in alert_fail.stdout
