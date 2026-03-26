from __future__ import annotations

import os

from core.system.action_validator import ActionValidator
from core.system.system_models import SystemAction, SystemActionType


def test_blocks_rm_rf_slash() -> None:
    validator = ActionValidator()
    action = SystemAction(
        SystemActionType.FILE_DELETE,
        params={"path": "/", "command": "rm -rf /"},
        destructive=True,
    )
    ok, reason = validator.validate(action)
    assert not ok
    assert "Blocked dangerous pattern" in reason


def test_blocks_sudo_command() -> None:
    validator = ActionValidator()
    action = SystemAction(SystemActionType.APP_LAUNCH, params={"command": "sudo reboot"})
    ok, reason = validator.validate(action)
    assert not ok
    assert "Blocked dangerous pattern" in reason


def test_blocks_path_outside_home() -> None:
    validator = ActionValidator()
    action = SystemAction(SystemActionType.FILE_DELETE, params={"path": "/etc/passwd"})
    ok, reason = validator.validate(action)
    assert not ok
    assert "outside safe boundaries" in reason


def test_allows_safe_file_move(tmp_path) -> None:
    validator = ActionValidator()
    source = tmp_path / "a.txt"
    destination = tmp_path / "b.txt"
    action = SystemAction(
        SystemActionType.FILE_MOVE,
        params={"source": str(source), "destination": str(destination)},
    )
    ok, reason = validator.validate(action)
    assert ok
    assert reason == "ok"


def test_allows_home_directory_operations() -> None:
    validator = ActionValidator()
    home_path = os.path.join(os.path.expanduser("~"), "Documents", "demo.txt")
    action = SystemAction(SystemActionType.FILE_CREATE, params={"path": home_path})
    ok, _ = validator.validate(action)
    assert ok


def test_marks_delete_as_requires_confirmation(tmp_path) -> None:
    validator = ActionValidator()
    action = SystemAction(
        SystemActionType.FILE_DELETE,
        params={"path": str(tmp_path / "demo.txt")},
        destructive=True,
        requires_confirmation=False,
    )
    ok, _ = validator.validate(action)
    assert ok
    assert action.requires_confirmation is True


def test_blocks_chmod_777_root() -> None:
    validator = ActionValidator()
    action = SystemAction(SystemActionType.APP_LAUNCH, params={"command": "chmod 777 /"})
    ok, reason = validator.validate(action)
    assert not ok
    assert "Blocked dangerous pattern" in reason


def test_allows_tmp_path(tmp_path) -> None:
    validator = ActionValidator()
    action = SystemAction(SystemActionType.FILE_CREATE, params={"path": str(tmp_path / "safe.txt")})
    ok, _ = validator.validate(action)
    assert ok


def test_blocks_critical_process_before_confirmation() -> None:
    validator = ActionValidator()
    action = SystemAction(
        SystemActionType.PROCESS_KILL,
        params={"pid_or_name": "systemd"},
        destructive=True,
        requires_confirmation=True,
    )
    ok, reason = validator.validate(action)
    assert not ok
    assert "critical process" in reason.lower()


def test_blocks_shell_command_dangerous_pattern() -> None:
    validator = ActionValidator()
    action = SystemAction(
        SystemActionType.SHELL_COMMAND,
        params={"command": "rm -rf /"},
    )
    ok, reason = validator.validate(action)
    assert not ok
    assert "Blocked dangerous pattern" in reason
