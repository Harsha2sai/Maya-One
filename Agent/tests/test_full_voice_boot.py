import os
import subprocess
import time
from unittest.mock import Mock


def test_full_voice_boot_smoke(monkeypatch):
    proc = Mock()
    proc.poll.side_effect = [None, 0]
    proc.wait.return_value = 0

    captured = {}

    def _fake_popen(cmd, env=None, stdout=None, stderr=None, text=None):
        captured["cmd"] = cmd
        captured["env"] = env
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["text"] = text
        return proc

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(os.path, "exists", lambda path: path == "venv/bin/python3")

    python_executable = "venv/bin/python3"
    env = os.environ.copy()
    env["PYTHONPATH"] = "."

    started = subprocess.Popen(
        [python_executable, "agent.py", "dev"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    time.sleep(15)

    if proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=5)

    assert started is proc
    assert captured["cmd"] == ["venv/bin/python3", "agent.py", "dev"]
    assert captured["env"]["PYTHONPATH"] == "."
    assert captured["stdout"] == subprocess.PIPE
    assert captured["stderr"] == subprocess.PIPE
    assert captured["text"] is True
    proc.terminate.assert_called_once()
    proc.wait.assert_called_once_with(timeout=5)
