from __future__ import annotations

import subprocess

from core.system.safe_shell import safe_shell


def test_blocks_sudo() -> None:
    ok, message = safe_shell("sudo ls")
    assert not ok
    assert "not permitted" in message


def test_blocks_mkfs() -> None:
    ok, message = safe_shell("mkfs.ext4 /dev/sda")
    assert not ok
    assert "not permitted" in message


def test_blocks_piped_sudo() -> None:
    ok, message = safe_shell("echo hi | sudo tee /tmp/x")
    assert not ok
    assert "not permitted" in message


def test_allows_ls(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess("ls", 0, stdout="a\nb", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, output = safe_shell("ls")
    assert ok
    assert output == "a\nb"


def test_allows_playerctl(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess("playerctl", 0, stdout="Playing", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, output = safe_shell("playerctl status")
    assert ok
    assert output == "Playing"


def test_timeout_handling(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="sleep", timeout=10)

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, output = safe_shell("sleep 60")
    assert not ok
    assert output == "Command timed out"


def test_blocks_dd() -> None:
    ok, message = safe_shell("dd if=/dev/zero of=/tmp/blob")
    assert not ok
    assert "not permitted" in message


def test_blocks_iptables() -> None:
    ok, message = safe_shell("iptables -L")
    assert not ok
    assert "not permitted" in message
