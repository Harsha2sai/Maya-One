from unittest.mock import AsyncMock

import pytest

from core.action.models import VerificationTier
from core.action.verifier import ActionVerifier


@pytest.mark.asyncio
async def test_verifier_marks_failed_when_tool_reports_failure() -> None:
    verifier = ActionVerifier()
    result = await verifier.verify(
        intent_id="intent_1",
        tool_name="open_app",
        args={"app_name": "firefox"},
        normalized_result={"success": False, "message": "Failed", "error_code": "tool_failed"},
    )
    assert result.tier == VerificationTier.failed
    assert result.verified is False


@pytest.mark.asyncio
async def test_verifier_open_app_strong_when_process_running() -> None:
    verifier = ActionVerifier()
    verifier._is_process_running = AsyncMock(  # type: ignore[attr-defined]
        return_value=(True, "pgrep_probe", {"platform": "linux"})
    )
    result = await verifier.verify(
        intent_id="intent_1",
        tool_name="open_app",
        args={"app_name": "firefox"},
        normalized_result={"success": True, "message": "Opened firefox"},
    )
    assert result.tier == VerificationTier.strong
    assert result.verified is True


@pytest.mark.asyncio
async def test_verifier_handles_unavailable_process_probe_as_inconclusive() -> None:
    verifier = ActionVerifier()
    verifier._is_process_running = AsyncMock(  # type: ignore[attr-defined]
        return_value=(False, "tasklist_unavailable", {"platform": "windows"})
    )
    result = await verifier.verify(
        intent_id="intent_2",
        tool_name="close_app",
        args={"app_name": "notepad"},
        normalized_result={"success": True, "message": "Closed notepad"},
    )
    assert result.tier == VerificationTier.inconclusive
    assert result.verified is False
    assert "unavailable" in result.method
