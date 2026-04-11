from core.action.adapters import from_direct_tool_intent, from_system_action, to_tool_receipt
from core.action.models import ActionIntent, VerificationResult, VerificationTier
from core.orchestrator.fast_path_router import DirectToolIntent


def test_action_intent_adapter_from_direct_tool_intent() -> None:
    direct = DirectToolIntent(
        tool="open_app",
        args={"app_name": "youtube"},
        template="Opening YouTube.",
        group="youtube",
    )
    intent = from_direct_tool_intent(
        direct,
        session_id="s1",
        turn_id="t1",
        trace_id="trace-1",
    )
    assert isinstance(intent, ActionIntent)
    assert intent.operation == "open_app"
    assert intent.target == "youtube"
    assert intent.source_route == "fast_path"


def test_action_intent_adapter_from_system_action() -> None:
    intent = from_system_action(
        {"action_type": "close_app", "target": "firefox", "confidence": 0.9},
        session_id="s1",
        turn_id="t1",
        trace_id="trace-2",
    )
    assert isinstance(intent, ActionIntent)
    assert intent.operation == "close_app"
    assert intent.target == "firefox"
    assert intent.requires_confirmation is True


def test_action_intent_adapter_preserves_zero_confidence_value() -> None:
    intent = from_system_action(
        {"action_type": "open_app", "target": "firefox", "confidence": 0},
        session_id="s1",
        turn_id="t1",
        trace_id="trace-3",
    )
    assert intent.confidence == 0.0


def test_action_intent_adapter_falls_back_on_invalid_confidence() -> None:
    intent = from_system_action(
        {"action_type": "open_app", "target": "firefox", "confidence": "not-a-number"},
        session_id="s1",
        turn_id="t1",
        trace_id="trace-4",
    )
    assert intent.confidence == 0.8


def test_tool_receipt_to_dict_includes_verification() -> None:
    verification = VerificationResult(
        intent_id="intent_1",
        tier=VerificationTier.strong,
        verified=True,
        confidence=0.95,
        method="pgrep_running",
        message="Verified process is running.",
    )
    receipt = to_tool_receipt(
        intent_id="intent_1",
        tool_name="open_app",
        raw_result={"success": True},
        normalized_result={"success": True, "message": "Opened firefox"},
        duration_ms=23,
        verification=verification,
    )
    payload = receipt.to_dict()
    assert payload["tool_name"] == "open_app"
    assert payload["status"] == "succeeded"
    assert payload["verification"]["tier"] == "strong"
