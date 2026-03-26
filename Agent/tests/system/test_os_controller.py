from __future__ import annotations

import subprocess

from core.system.os_controller import LinuxController, get_os_controller


def test_detects_x11_session(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert LinuxController().detect_session() == "x11"


def test_detects_wayland_session(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert LinuxController().detect_session() == "wayland"


def test_x11_uses_xdotool(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert LinuxController().get_display_server() == "xdotool"


def test_wayland_uses_ydotool(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert LinuxController().get_display_server() == "ydotool"


def test_singleton_pattern() -> None:
    assert get_os_controller() is get_os_controller()


def test_fallback_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert LinuxController().detect_session() == "x11"


def test_screenshot_path_is_tmp(monkeypatch, tmp_path) -> None:
    controller = LinuxController()
    captured = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    path = tmp_path / "shot.png"
    assert controller.screenshot(str(path))
    assert captured["cmd"] == ["scrot", str(path)]


def test_linux_controller_instantiates() -> None:
    assert isinstance(LinuxController(), LinuxController)
