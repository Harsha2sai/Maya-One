from typing import List

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.action.state_store import ActionStateStore
from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.orchestrator.fast_path_router import FastPathRouter


def _build_router_with_state(store: ActionStateStore, session_id: str):
    turn_state = {}

    def parse_multi_app(app_phrase: str) -> List[str]:
        del app_phrase
        return []

    def is_recall_exclusion_intent(_text: str) -> bool:
        return False

    def resolve_active_subject() -> str:
        return store.resolve_pronoun_sync(session_id, "it")

    router = FastPathRouter(
        turn_state=turn_state,
        parse_multi_app_fn=parse_multi_app,
        is_recall_exclusion_intent_fn=is_recall_exclusion_intent,
        resolve_active_subject_fn=resolve_active_subject,
    )
    return router


def test_transcript_platform_search_uses_action_state_subject() -> None:
    store = ActionStateStore()
    session_id = "s1"
    # Directly seed the subject for transcript-follow-up behavior.
    import asyncio

    asyncio.run(store.set_active_subject(session_id, subject="Iran and America war", query="iran and america war"))
    router = _build_router_with_state(store, session_id)
    intent = router.detect_direct_tool_intent("open the youtube and search about it", origin="voice")
    assert intent is not None
    assert intent.tool == "open_app"
    assert "iran and america war" in intent.args["app_name"].lower()


@pytest.mark.asyncio
async def test_transcript_also_instagram_rewrites_to_open_additive_app() -> None:
    orchestrator = AgentOrchestrator(SimpleNamespace(room=None), MagicMock())
    orchestrator._action_state_carryover_enabled = True
    orchestrator._action_state_store = ActionStateStore()
    await orchestrator._action_state_store.record_receipt(
        "console_session",
        type("ReceiptLike", (), {
            "tool_name": "open_app",
            "status": "succeeded",
            "success": True,
            "message": "Opened facebook",
            "normalized_result": {"app_name": "facebook"},
        })(),
    )
    rewritten = await orchestrator._apply_action_state_carryover("also Instagram")
    assert rewritten == "open facebook and instagram"


@pytest.mark.asyncio
async def test_transcript_close_them_rewrites_to_last_opened_app() -> None:
    orchestrator = AgentOrchestrator(SimpleNamespace(room=None), MagicMock())
    orchestrator._action_state_carryover_enabled = True
    orchestrator._action_state_store = ActionStateStore()
    await orchestrator._action_state_store.record_receipt(
        "console_session",
        type("ReceiptLike", (), {
            "tool_name": "open_app",
            "status": "succeeded",
            "success": True,
            "message": "Opened calculator",
            "normalized_result": {"app_name": "calculator"},
        })(),
    )
    rewritten = await orchestrator._apply_action_state_carryover("close them")
    assert rewritten == "close calculator"
