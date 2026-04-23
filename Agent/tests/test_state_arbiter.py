import re
from dataclasses import dataclass
from typing import Any

import pytest

from core.action.constants import ActionStateConfig
from core.action.state_store import ActionStateStore
from core.orchestrator.state_arbiter import StateArbiter


class _PronounStub:
    @staticmethod
    def has_pronoun(text: str) -> bool:
        return bool(re.search(r"\b(him|her|them|it|that|his|their)\b", str(text or "").lower()))


@dataclass
class _OwnerStub:
    store: ActionStateStore
    query_type: str = "general"
    session_id: str = "s1"
    recent_research: bool = True

    def __post_init__(self) -> None:
        self._action_state_store = self.store
        self._pronoun_rewriter = _PronounStub()
        self._conversation_history = [
            {"role": "assistant", "content": "Research summary", "route": "research"}
        ] if self.recent_research else []

    def _session_key_for_context(self, tool_context: Any = None) -> str:
        if tool_context is None:
            return self.session_id
        return str(getattr(tool_context, "session_id", self.session_id) or self.session_id)

    def _current_action_state_turn(self, tool_context: Any = None) -> int:
        return self.store.current_turn(self._session_key_for_context(tool_context))

    def _is_memory_relevant(self, text: str) -> bool:
        return "remember" in str(text or "").lower()

    async def _classify_memory_query_type_async(
        self,
        user_input: str,
        *,
        route_hint: str = "",
        session_id: str | None = None,
    ) -> str:
        del user_input, route_hint, session_id
        return self.query_type


def _sample_action() -> dict:
    return {
        "type": "set_reminder",
        "domain": "scheduling",
        "summary": "Reminder: call John at 5pm",
        "data": {"task": "call John", "time": "tomorrow at 5 pm"},
    }


def _sample_entity(value: str = "Narendra Modi") -> dict:
    return {
        "domain": "research",
        "value": value,
        "entity_type": "person",
        "source_query": f"tell me about {value}",
    }


@pytest.mark.asyncio
async def test_state_arbiter_explicit_identity_intent() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store)
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="what is your name",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "identity"
    assert decision.explicit_intent == "identity_self"


@pytest.mark.asyncio
async def test_state_arbiter_entity_followup_selected_when_active_entity_present() -> None:
    store = ActionStateStore(ActionStateConfig(active_entity_ttl_seconds=3600))
    owner = _OwnerStub(store=store)
    store.increment_turn("s1")
    store.set_active_entity("s1", _sample_entity())
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="tell me more about him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "entity_followup"


@pytest.mark.asyncio
async def test_state_arbiter_profile_self_reference_overrides_entity() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store, query_type="user_profile_recall")
    store.increment_turn("s1")
    store.set_active_entity("s1", _sample_entity())
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="what is my name",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "profile_recall"


@pytest.mark.asyncio
async def test_state_arbiter_ambiguous_entity_action_returns_clarify() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store)
    store.increment_turn("s1")
    store.set_active_entity("s1", _sample_entity())
    store.set_last_action("s1", _sample_action())
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="what about him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "clarify"
    assert "reminder" in decision.clarify_message.lower()


@pytest.mark.asyncio
async def test_state_arbiter_clarify_loop_breaker_promotes_best_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATE_ARBITER_CLARIFY_MAX_GENERIC_ATTEMPTS", "1")
    store = ActionStateStore()
    owner = _OwnerStub(store=store)
    store.increment_turn("s1")
    store.set_active_entity("s1", _sample_entity())
    store.set_last_action("s1", _sample_action())
    arbiter = StateArbiter(owner=owner)

    first = await arbiter.arbitrate_turn(
        message="what about him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )
    second = await arbiter.arbitrate_turn(
        message="what about him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert first.owner == "clarify"
    assert second.owner in {"entity_followup", "action_followup"}
