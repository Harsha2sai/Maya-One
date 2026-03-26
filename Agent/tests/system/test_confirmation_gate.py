from __future__ import annotations

import asyncio

import pytest

from core.system.confirmation_gate import ConfirmationGate
from core.system.system_models import ConfirmationState, SystemAction, SystemActionType


@pytest.mark.asyncio
async def test_timeout_resolves_to_rejected(monkeypatch) -> None:
    monkeypatch.setattr(ConfirmationGate, "TIMEOUT_SECONDS", 0.01)
    action = SystemAction(SystemActionType.FILE_DELETE, requires_confirmation=True, trace_id="t1")
    state = await ConfirmationGate.request(action)
    assert state == ConfirmationState.TIMEOUT


@pytest.mark.asyncio
async def test_confirmed_resolves_correctly() -> None:
    action = SystemAction(SystemActionType.FILE_DELETE, requires_confirmation=True, trace_id="t2")

    async def respond() -> None:
        await asyncio.sleep(0.01)
        ConfirmationGate.respond("t2", True)

    asyncio.create_task(respond())
    state = await ConfirmationGate.request(action)
    assert state == ConfirmationState.CONFIRMED


@pytest.mark.asyncio
async def test_cancelled_resolves_correctly() -> None:
    action = SystemAction(SystemActionType.FILE_DELETE, requires_confirmation=True, trace_id="t3")

    async def respond() -> None:
        await asyncio.sleep(0.01)
        ConfirmationGate.respond("t3", False)

    asyncio.create_task(respond())
    state = await ConfirmationGate.request(action)
    assert state == ConfirmationState.REJECTED


@pytest.mark.asyncio
async def test_non_destructive_skips_gate() -> None:
    action = SystemAction(SystemActionType.SCREENSHOT, requires_confirmation=False, trace_id="t4")
    state = await ConfirmationGate.request(action)
    assert state == ConfirmationState.CONFIRMED


@pytest.mark.asyncio
async def test_multiple_pending_independent() -> None:
    first = SystemAction(SystemActionType.FILE_DELETE, requires_confirmation=True, trace_id="t5")
    second = SystemAction(SystemActionType.FILE_DELETE, requires_confirmation=True, trace_id="t6")

    async def respond() -> None:
        await asyncio.sleep(0.01)
        ConfirmationGate.respond("t5", True)
        ConfirmationGate.respond("t6", False)

    asyncio.create_task(respond())
    first_state, second_state = await asyncio.gather(
        ConfirmationGate.request(first),
        ConfirmationGate.request(second),
    )
    assert first_state == ConfirmationState.CONFIRMED
    assert second_state == ConfirmationState.REJECTED


def test_timeout_is_30_seconds() -> None:
    assert ConfirmationGate.TIMEOUT_SECONDS == 30


@pytest.mark.asyncio
async def test_gate_cleans_up_after_response() -> None:
    action = SystemAction(SystemActionType.FILE_DELETE, requires_confirmation=True, trace_id="t7")

    async def respond() -> None:
        await asyncio.sleep(0.01)
        ConfirmationGate.respond("t7", True)

    asyncio.create_task(respond())
    await ConfirmationGate.request(action)
    assert "t7" not in ConfirmationGate._pending


@pytest.mark.asyncio
async def test_gate_cleans_up_after_timeout(monkeypatch) -> None:
    monkeypatch.setattr(ConfirmationGate, "TIMEOUT_SECONDS", 0.01)
    action = SystemAction(SystemActionType.FILE_DELETE, requires_confirmation=True, trace_id="t8")
    await ConfirmationGate.request(action)
    assert "t8" not in ConfirmationGate._pending
