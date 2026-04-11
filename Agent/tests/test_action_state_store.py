import asyncio

import pytest

from core.action.constants import ActionStateConfig
from core.action.models import ActionIntent
from core.action.state_store import ActionStateStore


@pytest.mark.asyncio
async def test_action_state_store_records_and_resolves_subject() -> None:
    store = ActionStateStore(ActionStateConfig(default_ttl_seconds=300, search_query_ttl_seconds=600))
    await store.set_active_subject("s1", subject="Iran America war", query="iran america war latest")

    resolved = await store.resolve_pronoun("s1", "it")
    assert resolved == "Iran America war"


@pytest.mark.asyncio
async def test_action_state_store_additive_and_continuation_resolution() -> None:
    store = ActionStateStore()
    await store.record_intent(
        "s1",
        ActionIntent(
            intent_id="i1",
            session_id="s1",
            turn_id="t1",
            trace_id="tr1",
            source_route="fast_path",
            target="facebook",
            operation="open_app",
            entity="app",
            query="",
            confidence=1.0,
            requires_confirmation=False,
        ),
    )
    await store.record_receipt(
        "s1",
        type("ReceiptLike", (), {
            "tool_name": "open_app",
            "status": "succeeded",
            "success": True,
            "message": "Opened facebook",
            "normalized_result": {"app_name": "facebook"},
        })(),
    )
    await store.set_active_subject("s1", subject="coal price drop", query="coal price drop")

    additive = await store.resolve_additive("s1", "also instagram")
    assert additive == "facebook and instagram"

    continuation = await store.resolve_continuation("s1", "open videos about it in youtube")
    assert continuation == "coal price drop"


@pytest.mark.asyncio
async def test_action_state_store_reuses_single_lock_for_same_session() -> None:
    store = ActionStateStore()
    lock_ids = set()

    async def _touch() -> None:
        lock_ids.add(id(store._lock_for("s-lock")))  # noqa: SLF001 - testing internal lock behavior
        await store.mark_turn_start("s-lock", "turn-1", "hello")

    await asyncio.gather(*[_touch() for _ in range(20)])
    assert len(lock_ids) == 1
