from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _script_path() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "export_agent_event_schema.py"


def test_export_schema_writes_output(tmp_path: Path) -> None:
    output_path = tmp_path / "agent_events.schema.v1.json"
    result = subprocess.run(
        [
            sys.executable,
            str(_script_path()),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output_path.exists()
    text = output_path.read_text(encoding="utf-8")
    assert "schema_version" in text
    assert "agent_thinking" in text
    assert "research_result" in text
    assert "media_result" in text


def test_export_schema_check_mode_detects_drift(tmp_path: Path) -> None:
    output_path = tmp_path / "agent_events.schema.v1.json"
    output_path.write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(_script_path()),
            "--check",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "schema drift detected" in result.stdout
