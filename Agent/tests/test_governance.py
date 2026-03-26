
import sys
import os
import unittest
from typing import Dict, Any

# Ensure we can import from the Agent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.governance.types import UserRole, RiskLevel
from core.governance.policy import ToolRiskPolicy
from core.governance.gate import ExecutionGate
from core.governance.audit import AuditLogger

class TestGovernance(unittest.TestCase):

    def test_risk_level_mapping(self):
        """Test that tools are correctly mapped to risk levels"""
        self.assertEqual(ToolRiskPolicy.get_risk("get_time"), RiskLevel.READ_ONLY)
        self.assertEqual(ToolRiskPolicy.get_risk("get_weather"), RiskLevel.LOW)
        self.assertEqual(ToolRiskPolicy.get_risk("list_notes"), RiskLevel.MEDIUM)
        self.assertEqual(ToolRiskPolicy.get_risk("send_email"), RiskLevel.HIGH)
        # Undefined tools should default to HIGH
        self.assertEqual(ToolRiskPolicy.get_risk("unknown_tool"), RiskLevel.HIGH)

    def test_user_role_max_risk(self):
        """Test that user roles map to correct max risk levels"""
        self.assertEqual(UserRole.GUEST.max_risk, RiskLevel.LOW)
        self.assertEqual(UserRole.USER.max_risk, RiskLevel.MEDIUM)
        self.assertEqual(UserRole.TRUSTED.max_risk, RiskLevel.HIGH)
        self.assertEqual(UserRole.ADMIN.max_risk, RiskLevel.CRITICAL)

    def test_execution_gate_guest(self):
        """Test GUEST access control"""
        role = UserRole.GUEST
        
        # Should allow
        self.assertTrue(ExecutionGate.check_access("get_time", role))
        self.assertTrue(ExecutionGate.check_access("get_weather", role))
        
        # Should block
        self.assertFalse(ExecutionGate.check_access("list_notes", role))
        self.assertFalse(ExecutionGate.check_access("send_email", role))
        self.assertFalse(ExecutionGate.check_access("unknown_tool", role))

    def test_execution_gate_admin(self):
        """Test ADMIN access control"""
        role = UserRole.ADMIN
        
        # Should allow everything
        self.assertTrue(ExecutionGate.check_access("get_time", role))
        self.assertTrue(ExecutionGate.check_access("list_notes", role))
        self.assertTrue(ExecutionGate.check_access("send_email", role))
        self.assertTrue(ExecutionGate.check_access("system_shutdown", role))

    def test_audit_logger_format(self):
        """Test that audit logger produces trace IDs"""
        trace_id = AuditLogger.log_attempt(
            tool_name="test_tool",
            params={"a": 1},
            user_role=UserRole.ADMIN,
            user_id="test_user"
        )
        self.assertIsNotNone(trace_id)
        self.assertIsInstance(trace_id, str)
        self.assertGreater(len(trace_id), 0)

if __name__ == '__main__':
    unittest.main()
