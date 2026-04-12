import pytest

from core.action.models import VerificationTier
from core.action.verifier import ActionVerifier, categorize_shell_error
import core.action.verifier as verifier_mod


def test_categorize_shell_error_command_not_found() -> None:
    code = categorize_shell_error("foo_bar_cmd --arg", "bash: foo_bar_cmd: command not found")
    assert code.startswith("command_not_found:")


@pytest.mark.asyncio
async def test_shell_verification_inconclusive_without_output() -> None:
    verifier = ActionVerifier()
    result = await verifier.verify(
        intent_id="intent_2",
        tool_name="run_shell_command",
        args={"command": "echo"},
        normalized_result={"success": True, "message": ""},
        raw_result="",
    )
    assert result.tier in {VerificationTier.inconclusive, VerificationTier.medium}


@pytest.mark.asyncio
async def test_process_probe_uses_windows_tasklist_when_psutil_missing(monkeypatch) -> None:
    verifier = ActionVerifier()
    monkeypatch.setattr(verifier_mod, "psutil", None)
    monkeypatch.setattr(verifier_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        ActionVerifier,
        "_tasklist_process_running",
        staticmethod(lambda _name: (True, True)),
    )
    running, method, evidence = await verifier._is_process_running("notepad")  # noqa: SLF001
    assert running is True
    assert method == "tasklist_probe"
    assert evidence["platform"] == "windows"
