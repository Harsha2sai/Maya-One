from __future__ import annotations

import os
import signal
import subprocess

from core.system.controllers.process_controller import PROCESS_KILL_DENYLIST, ProcessController
from core.system.system_models import SystemAction, SystemActionType


def test_blocks_kill_systemd() -> None:
    controller = ProcessController()
    action = SystemAction(SystemActionType.PROCESS_KILL, params={"pid_or_name": "systemd"})
    result = controller.kill_process(action)
    assert not result.success
    assert "critical to your system" in result.message


def test_blocks_kill_xorg() -> None:
    controller = ProcessController()
    action = SystemAction(SystemActionType.PROCESS_KILL, params={"pid_or_name": "Xorg"})
    result = controller.kill_process(action)
    assert not result.success


def test_blocks_kill_dbus() -> None:
    controller = ProcessController()
    action = SystemAction(SystemActionType.PROCESS_KILL, params={"pid_or_name": "dbus"})
    result = controller.kill_process(action)
    assert not result.success


def test_allows_kill_user_process(monkeypatch) -> None:
    controller = ProcessController()
    monkeypatch.setattr(controller, "_find_pid_by_name", lambda _name: (4321, "custom-app"))
    captured = {}

    def fake_kill(pid: int, sig: int) -> None:
        captured["pid"] = pid
        captured["sig"] = sig

    monkeypatch.setattr(os, "kill", fake_kill)
    action = SystemAction(SystemActionType.PROCESS_KILL, params={"pid_or_name": "custom-app"})
    result = controller.kill_process(action)
    assert result.success
    assert captured == {"pid": 4321, "sig": signal.SIGTERM}


def test_denylist_is_complete() -> None:
    assert "systemd" in PROCESS_KILL_DENYLIST
    assert "dbus" in PROCESS_KILL_DENYLIST
    assert "Xorg" in PROCESS_KILL_DENYLIST


def test_uses_sigterm_not_sigkill(monkeypatch) -> None:
    controller = ProcessController()
    monkeypatch.setattr(controller, "_find_pid_by_name", lambda _name: (1234, "custom-app"))
    captured = {}

    def fake_kill(pid: int, sig: int) -> None:
        captured["sig"] = sig

    monkeypatch.setattr(os, "kill", fake_kill)
    action = SystemAction(SystemActionType.PROCESS_KILL, params={"pid_or_name": "custom-app"})
    controller.kill_process(action)
    assert captured["sig"] == signal.SIGTERM


def test_list_processes_returns_results(monkeypatch) -> None:
    controller = ProcessController()

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess("ps", 0, stdout=" 1 init\n 2 bash", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    action = SystemAction(SystemActionType.PROCESS_LIST)
    result = controller.list_processes(action)
    assert result.success
    assert "bash" in result.detail


def test_kill_requires_confirmation() -> None:
    action = SystemAction(
        SystemActionType.PROCESS_KILL,
        params={"pid_or_name": "custom-app"},
        destructive=True,
        requires_confirmation=True,
    )
    assert action.destructive is True
    assert action.requires_confirmation is True
