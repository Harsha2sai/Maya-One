from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from core.ide import (
    ActionEnvelope,
    ActionGuard,
    IDEFileService,
    IDESessionManager,
    IDEStateBus,
    MaxSessionsExceededError,
    PathEscapeError,
)


def _open_workspace_session(tmp_path: Path) -> tuple[IDESessionManager, IDEFileService, str]:
    manager = IDESessionManager(max_concurrent=5)
    service = IDEFileService(manager)
    session = manager.open_session(str(tmp_path), user_id="u1")
    return manager, service, session.session_id


def test_open_and_close_session(tmp_path: Path):
    manager = IDESessionManager(max_concurrent=5)
    session = manager.open_session(str(tmp_path), user_id="u1")
    assert session.status == "open"
    assert manager.get_session(session.session_id) is not None

    assert manager.close_session(session.session_id) is True
    assert manager.get_session(session.session_id) is None


def test_file_read_within_workspace(tmp_path: Path):
    manager, service, session_id = _open_workspace_session(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("hello maya", encoding="utf-8")

    assert service.read_file(session_id, "notes.txt") == "hello maya"
    assert manager.get_session(session_id) is not None


def test_file_write_within_workspace(tmp_path: Path):
    _manager, service, session_id = _open_workspace_session(tmp_path)
    assert service.write_file(session_id, "src/main.py", "print('ok')") is True
    assert (tmp_path / "src/main.py").read_text(encoding="utf-8") == "print('ok')"


def test_path_traversal_rejected(tmp_path: Path):
    _manager, service, session_id = _open_workspace_session(tmp_path)
    with pytest.raises(PathEscapeError):
        service.read_file(session_id, "../etc/passwd")


def test_action_guard_low_risk_allowed():
    guard = ActionGuard()
    decision = guard.check(
        ActionEnvelope(
            type="ide_action",
            target="file",
            operation="read",
            arguments={"relative_path": "README.md"},
            confidence=0.99,
            reason="read",
        )
    )
    assert decision.risk == "low"
    assert decision.allowed is True
    assert decision.requires_approval is False


def test_action_guard_high_risk_requires_approval():
    guard = ActionGuard()
    decision = guard.check(
        ActionEnvelope(
            type="ide_action",
            target="terminal",
            operation="exec",
            arguments={"cmd": "rm -rf build"},
            confidence=0.71,
            reason="run command",
        )
    )
    assert decision.risk == "high"
    assert decision.allowed is True
    assert decision.requires_approval is True


def test_action_guard_traversal_denied():
    guard = ActionGuard()
    decision = guard.check(
        {
            "type": "ide_action",
            "target": "file",
            "operation": "write",
            "arguments": {"relative_path": "../secrets.txt"},
            "confidence": 0.87,
            "reason": "unsafe path",
        }
    )
    assert decision.risk == "high"
    assert decision.allowed is False
    assert decision.requires_approval is False


@pytest.mark.asyncio
async def test_state_bus_emits_on_file_write():
    bus = IDEStateBus()
    queue = bus.subscribe()

    await bus.emit("file_written", {"session_id": "s1", "path": "main.py"})
    event = await queue.get()
    assert event["event_type"] == "file_written"
    assert event["payload"]["path"] == "main.py"


def test_max_concurrent_sessions_enforced(tmp_path: Path):
    manager = IDESessionManager(max_concurrent=5)
    for index in range(5):
        workspace = tmp_path / f"ws_{index}"
        workspace.mkdir(parents=True, exist_ok=True)
        manager.open_session(str(workspace), user_id=f"user_{index}")

    extra = tmp_path / "overflow"
    extra.mkdir(parents=True, exist_ok=True)
    with pytest.raises(MaxSessionsExceededError):
        manager.open_session(str(extra), user_id="overflow")


def test_session_ttl_evicts_on_access(tmp_path: Path):
    manager = IDESessionManager(max_concurrent=5, session_ttl_seconds=1)
    session = manager.open_session(str(tmp_path), user_id="u1")
    session.created_at_epoch_s = time.time() - 120

    assert manager.get_session(session.session_id) is None


@pytest.mark.asyncio
async def test_session_cleanup_loop_evicts_expired(tmp_path: Path):
    manager = IDESessionManager(
        max_concurrent=5, session_ttl_seconds=1, cleanup_interval_seconds=1
    )
    session = manager.open_session(str(tmp_path), user_id="u1")
    session.created_at_epoch_s = time.time() - 120

    await manager.start_cleanup()
    await asyncio.sleep(1.2)
    await manager.stop_cleanup()

    assert manager.get_session(session.session_id) is None
