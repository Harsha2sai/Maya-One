import re
from types import SimpleNamespace

from config.settings import settings
from core.orchestrator.tool_response_builder import ToolResponseBuilder


def _builder() -> ToolResponseBuilder:
    owner = SimpleNamespace(_TOOL_ERROR_HINT_PATTERN=re.compile(r"(error|traceback|exception)", re.IGNORECASE))
    return ToolResponseBuilder(owner=owner)


def test_normalize_tool_result_uses_receipt_failed_status() -> None:
    builder = _builder()
    result = builder.normalize_tool_result(
        tool_name="open_app",
        raw_result={
            "success": True,
            "message": "Opened firefox",
            "_tool_receipt": {"status": "failed"},
        },
    )
    assert result["success"] is False
    assert result["error_code"] == "tool_failed"


def test_get_tool_response_template_strict_mode_uses_uncertain_wording(monkeypatch) -> None:
    builder = _builder()
    monkeypatch.setattr(settings, "action_truthfulness_strict", True)

    uncertain = builder.get_tool_response_template(
        "open_app",
        {
            "app_name": "firefox",
            "_tool_receipt": {"verification": {"tier": "medium"}},
        },
        mode="direct",
    )
    assert "couldn't verify" in (uncertain or "").lower()

    strong = builder.get_tool_response_template(
        "open_app",
        {
            "app_name": "firefox",
            "_tool_receipt": {"verification": {"tier": "strong"}},
        },
        mode="direct",
    )
    assert strong == "Opened firefox."

