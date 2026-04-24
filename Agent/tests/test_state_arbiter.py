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
    assert decision.clarify_reason == "cross_domain_pronoun_conflict"
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
    third = await arbiter.arbitrate_turn(
        message="what about him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert first.owner == "clarify"
    assert second.owner == "clarify"
    assert second.reason == "clarify_loop_hard_prompt"
    assert third.owner in {"clarify", "entity_followup", "action_followup"}
    if third.owner == "clarify":
        assert third.reason == "clarify_loop_hard_prompt"


@pytest.mark.asyncio
async def test_state_arbiter_first_turn_research_entry_sets_metadata() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store, recent_research=False)
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="tell me about Elon Musk",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "entity_followup"
    assert decision.reason == "explicit_research_entry"
    assert decision.meta["is_research_entry"] is True


@pytest.mark.asyncio
async def test_state_arbiter_reminder_followup_dominates_scheduling_command() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store)
    store.increment_turn("s1")
    store.set_last_action("s1", _sample_action())
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="what reminder did I set",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "action_followup"
    assert decision.reason == "context_dominant_action_followup"


@pytest.mark.asyncio
async def test_state_arbiter_noisy_reminder_followup_maps_to_action_path() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store)
    store.increment_turn("s1")
    store.set_last_action("s1", _sample_action())
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="reminder uh what did I set",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "action_followup"


@pytest.mark.asyncio
async def test_state_arbiter_declarative_profile_statement_returns_general_chat() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store, recent_research=False)
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="my name is Harsha",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "general_chat"
    assert decision.reason == "declarative_profile_update"


@pytest.mark.asyncio
async def test_state_arbiter_programming_context_returns_general_chat() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store, recent_research=False)
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="what is my name in python",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "general_chat"


@pytest.mark.asyncio
async def test_state_arbiter_programming_context_beats_profile_statement() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store, recent_research=False)
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="my name is Harsha in python",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "general_chat"


@pytest.mark.asyncio
async def test_state_arbiter_non_followup_command_after_research_does_not_resolve_entity() -> None:
    store = ActionStateStore(ActionStateConfig(active_entity_ttl_seconds=3600))
    owner = _OwnerStub(store=store, recent_research=True)
    store.increment_turn("s1")
    store.set_active_entity("s1", _sample_entity("Tesla"))
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="open youtube",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner != "entity_followup"


@pytest.mark.asyncio
async def test_state_arbiter_clarify_loop_second_attempt_is_guided_or_fallback() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store, recent_research=False)
    arbiter = StateArbiter(owner=owner)

    first = await arbiter.arbitrate_turn(
        message="what about him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )
    second = await arbiter.arbitrate_turn(
        message="him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert first.owner == "clarify"
    assert second.owner in {"clarify", "entity_followup", "action_followup"}
    if second.owner == "clarify":
        assert second.reason in {"clarify_loop_hard_prompt", "clarify_required"}


@pytest.mark.asyncio
async def test_state_arbiter_pronoun_without_anchor_clarifies() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store, recent_research=False)
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="what about him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "clarify"


@pytest.mark.asyncio
async def test_state_arbiter_cross_domain_pronoun_conflict_is_deterministic_without_score_gate() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store)
    store.increment_turn("s1")
    store.set_active_entity("s1", _sample_entity())
    store.set_last_action("s1", _sample_action())
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "clarify"
    assert decision.clarify_reason == "cross_domain_pronoun_conflict"


@pytest.mark.asyncio
async def test_state_arbiter_drifted_entity_pronoun_does_not_win() -> None:
    store = ActionStateStore(
        ActionStateConfig(
            active_entity_ttl_seconds=3600,
            active_entity_max_turns=10,
            active_entity_max_non_research_turns=0,
        )
    )
    owner = _OwnerStub(store=store, recent_research=True)
    store.increment_turn("s1")
    store.set_active_entity("s1", _sample_entity())
    store.mark_route_turn_sync("s1", "chat")
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="what about it",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "clarify"


@pytest.mark.asyncio
async def test_state_arbiter_multi_entity_followup_clarifies() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store, recent_research=True)
    owner._conversation_history = [
        {"role": "user", "content": "tell me about Modi and Elon Musk", "route": "research"},
        {"role": "assistant", "content": "Research summary", "route": "research"},
    ]
    arbiter = StateArbiter(owner=owner)

    decision = await arbiter.arbitrate_turn(
        message="what about him",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.owner == "clarify"


@pytest.mark.asyncio
async def test_state_arbiter_clarify_context_does_not_leak_into_research_entry() -> None:
    store = ActionStateStore()
    owner = _OwnerStub(store=store, recent_research=False)
    arbiter = StateArbiter(owner=owner)
    arbiter._set_clarify_context(
        session_key="s1",
        payload={
            "reason": "low_confidence",
            "candidate_owners": ["general_chat", "profile_recall"],
            "best_owner": "general_chat",
            "attempt_count": 1,
            "written_turn": 0,
        },
    )

    decision = await arbiter.arbitrate_turn(
        message="tell me about Tesla",
        origin="chat",
        tool_context=None,
        user_id="u1",
    )

    assert decision.reason == "explicit_research_entry"
    assert decision.owner == "entity_followup"
