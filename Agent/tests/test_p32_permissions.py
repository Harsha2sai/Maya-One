"""
P32 permission system tests.
Validates risk policy registration, mode switching, and gate behavior.
"""

import pytest
from core.governance.gate import ExecutionGate
from core.governance.policy import ToolRiskPolicy
from core.governance.types import UserRole, RiskLevel
from core.permissions.contracts import PermissionMode, PermissionChecker, PermissionConfig


@pytest.fixture(autouse=True)
def reset_gate():
    """Reset ExecutionGate to default state after every test."""
    yield
    ExecutionGate.reset_mode()


# ── P31 tool risk registration ────────────────────────────────────────────────

def test_file_read_is_low_risk():
    assert ToolRiskPolicy.get_risk("file_read") == RiskLevel.LOW

def test_file_glob_is_low_risk():
    assert ToolRiskPolicy.get_risk("file_glob") == RiskLevel.LOW

def test_file_grep_is_low_risk():
    assert ToolRiskPolicy.get_risk("file_grep") == RiskLevel.LOW

def test_file_edit_is_high_risk():
    assert ToolRiskPolicy.get_risk("file_edit") == RiskLevel.HIGH

def test_file_write_p31_is_high_risk():
    assert ToolRiskPolicy.get_risk("file_write") == RiskLevel.HIGH

def test_bash_is_critical_risk():
    assert ToolRiskPolicy.get_risk("bash") == RiskLevel.CRITICAL

def test_spawn_subagent_is_high_risk():
    assert ToolRiskPolicy.get_risk("spawn_subagent") == RiskLevel.HIGH

def test_check_agent_result_is_low_risk():
    assert ToolRiskPolicy.get_risk("check_agent_result") == RiskLevel.LOW


# ── Role-based access with registered tools ───────────────────────────────────

def test_user_role_can_access_low_risk_tool():
    # USER max_risk = MEDIUM, file_read = LOW → allowed
    assert ExecutionGate.check_access("file_read", UserRole.USER) is True

def test_user_role_blocked_from_critical_tool():
    # USER max_risk = MEDIUM, bash = CRITICAL → blocked
    assert ExecutionGate.check_access("bash", UserRole.USER) is False

def test_admin_role_can_access_bash():
    # ADMIN max_risk = CRITICAL → allowed
    assert ExecutionGate.check_access("bash", UserRole.ADMIN) is True

def test_guest_role_blocked_from_medium_tool():
    # GUEST max_risk = LOW, send_agent_message = MEDIUM → blocked
    assert ExecutionGate.check_access("send_agent_message", UserRole.GUEST) is False


# ── Mode switching ────────────────────────────────────────────────────────────

def test_set_mode_updates_active_mode():
    ExecutionGate.set_mode(PermissionMode.ACCEPT_EDITS)
    assert ExecutionGate.get_mode() == PermissionMode.ACCEPT_EDITS

def test_reset_mode_returns_to_default():
    ExecutionGate.set_mode(PermissionMode.BYPASS)
    ExecutionGate.reset_mode()
    assert ExecutionGate.get_mode() == PermissionMode.DEFAULT

def test_locked_mode_blocks_all_tools():
    ExecutionGate.set_mode(PermissionMode.LOCKED)
    # Even ADMIN is blocked in LOCKED mode via mode policy
    checker = ExecutionGate._permission_checker
    result = checker.check(
        "file_read",
        UserRole.ADMIN,
        {"mode": PermissionMode.LOCKED, "respect_mode_policy": True},
    )
    assert result.allowed is False
    assert "locked" in result.reason.lower()

def test_bypass_mode_allows_everything():
    # Use ADMIN to clear role-risk gate, then verify mode policy allows
    checker = ExecutionGate._permission_checker
    result = checker.check(
        "bash",
        UserRole.ADMIN,
        {"mode": PermissionMode.BYPASS, "respect_mode_policy": True},
    )
    assert result.allowed is True

def test_plan_mode_blocks_execution():
    checker = ExecutionGate._permission_checker
    result = checker.check(
        "file_read",   # LOW risk — clears role-risk gate for any role
        UserRole.ADMIN,
        {"mode": PermissionMode.PLAN, "respect_mode_policy": True},
    )
    assert result.allowed is False
    assert "plan" in result.reason.lower()

def test_accept_edits_mode_blocks_shell():
    checker = ExecutionGate._permission_checker
    result = checker.check(
        "bash",
        UserRole.ADMIN,
        {"mode": PermissionMode.ACCEPT_EDITS, "respect_mode_policy": True},
    )
    assert result.allowed is False

def test_accept_edits_mode_allows_file_edit():
    checker = ExecutionGate._permission_checker
    result = checker.check(
        "file_edit",
        UserRole.ADMIN,
        {
            "mode": PermissionMode.ACCEPT_EDITS,
            "respect_mode_policy": True,
            "file_path": "/tmp/test.py",
        },
    )
    assert result.allowed is True


# ── Permission hook blocking ──────────────────────────────────────────────────

def test_pre_tool_hook_can_block_execution():
    from core.permissions.contracts import PermissionHook, PermissionHookType

    def blocking_handler(request, context):
        return {"allow": False, "reason": "test_block"}

    hook = PermissionHook(
        name="test_blocker",
        hook_type=PermissionHookType.PRE_TOOL_USE,
        handler=blocking_handler,
        priority=10,
    )

    checker = PermissionChecker()
    checker.register_hook(hook)

    result = checker.check("file_read", UserRole.ADMIN, {})
    assert result.allowed is False
    assert "test_block" in result.reason
