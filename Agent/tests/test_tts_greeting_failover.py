import asyncio

import pytest

from agent import _speak_greeting_with_failover


class _FakeSession:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    async def say(self, _text, allow_interruptions=True, add_to_chat_ctx=True):
        del allow_interruptions, add_to_chat_ctx
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome == "slow":
            await asyncio.sleep(0.05)
            return
        return


@pytest.mark.asyncio
async def test_greeting_primary_failure_triggers_failover_then_succeeds():
    active_provider = {"name": "elevenlabs"}
    failover_reasons = []
    session = _FakeSession([RuntimeError("primary failed"), "ok"])

    async def _failover_handler(reason: str) -> None:
        failover_reasons.append(reason)
        active_provider["name"] = "edge_tts"

    await _speak_greeting_with_failover(
        session=session,
        greeting_text="hello",
        timeout_s=0.5,
        get_active_tts_provider=lambda: active_provider["name"],
        failover_handler=_failover_handler,
    )

    assert failover_reasons == ["primary failed"]
    assert session.calls == 2
    assert active_provider["name"] == "edge_tts"


@pytest.mark.asyncio
async def test_greeting_both_providers_fail_silent_drop():
    active_provider = {"name": "elevenlabs"}
    failover_reasons = []
    session = _FakeSession([RuntimeError("primary failed"), RuntimeError("fallback failed")])

    async def _failover_handler(reason: str) -> None:
        failover_reasons.append(reason)
        active_provider["name"] = "edge_tts"

    await _speak_greeting_with_failover(
        session=session,
        greeting_text="hello",
        timeout_s=0.5,
        get_active_tts_provider=lambda: active_provider["name"],
        failover_handler=_failover_handler,
    )

    assert failover_reasons == ["primary failed"]
    assert session.calls == 2


@pytest.mark.asyncio
async def test_greeting_timeout_does_not_trigger_failover():
    failover_reasons = []
    session = _FakeSession(["slow"])

    async def _failover_handler(reason: str) -> None:
        failover_reasons.append(reason)

    await _speak_greeting_with_failover(
        session=session,
        greeting_text="hello",
        timeout_s=0.01,
        get_active_tts_provider=lambda: "edge_tts",
        failover_handler=_failover_handler,
    )

    assert failover_reasons == []
    assert session.calls == 1
