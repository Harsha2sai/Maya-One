import subprocess
import inspect
from unittest.mock import MagicMock

import pytest

from tools.system import pc_control


async def _call_run_shell(command: str):
    result = pc_control.run_shell_command._func(None, command)
    if inspect.isawaitable(result):
        return await result
    return result


@pytest.mark.asyncio
async def test_single_word_non_shell_utility_uses_popen(monkeypatch: pytest.MonkeyPatch):
    popen_mock = MagicMock()
    run_mock = MagicMock()
    monkeypatch.setattr(pc_control.subprocess, "Popen", popen_mock)
    monkeypatch.setattr(pc_control.subprocess, "run", run_mock)

    result = await _call_run_shell("firefox")

    assert result == "Launched successfully."
    popen_mock.assert_called_once()
    run_mock.assert_not_called()


@pytest.mark.asyncio
async def test_single_word_shell_utility_uses_blocking_run(monkeypatch: pytest.MonkeyPatch):
    popen_mock = MagicMock()
    run_mock = MagicMock(
        return_value=subprocess.CompletedProcess(args="ls", returncode=0, stdout="file.txt\n", stderr="")
    )
    monkeypatch.setattr(pc_control.subprocess, "Popen", popen_mock)
    monkeypatch.setattr(pc_control.subprocess, "run", run_mock)

    result = await _call_run_shell("ls")

    assert "file.txt" in result
    run_mock.assert_called_once()
    popen_mock.assert_not_called()


@pytest.mark.asyncio
async def test_pipe_command_uses_blocking_run(monkeypatch: pytest.MonkeyPatch):
    popen_mock = MagicMock()
    run_mock = MagicMock(
        return_value=subprocess.CompletedProcess(args="ls | wc -l", returncode=0, stdout="5\n", stderr="")
    )
    monkeypatch.setattr(pc_control.subprocess, "Popen", popen_mock)
    monkeypatch.setattr(pc_control.subprocess, "run", run_mock)

    result = await _call_run_shell("ls | wc -l")

    assert result.strip() == "5"
    run_mock.assert_called_once()
    popen_mock.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_single_word_command_uses_popen(monkeypatch: pytest.MonkeyPatch):
    popen_mock = MagicMock()
    run_mock = MagicMock()
    monkeypatch.setattr(pc_control.subprocess, "Popen", popen_mock)
    monkeypatch.setattr(pc_control.subprocess, "run", run_mock)

    result = await _call_run_shell("obsidian")

    assert result == "Launched successfully."
    popen_mock.assert_called_once()
    run_mock.assert_not_called()
