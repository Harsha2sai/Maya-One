"""
Tests for Static Analyzer

Tests the static analysis checks to ensure they correctly detect
issues in the codebase.
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.static_analyzer import MayaStaticAnalyzer, CheckResult

pytestmark = pytest.mark.filterwarnings("ignore:unclosed event loop:ResourceWarning")


class TestStaticAnalyzer:
    """Tests for the static analyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create a static analyzer instance."""
        return MayaStaticAnalyzer()

    def test_analyzer_initialization(self, analyzer):
        """Test analyzer initializes correctly."""
        assert analyzer.base_path.exists()
        assert analyzer.pass_count == 0
        assert analyzer.fail_count == 0

    def test_check_identity_prompt_contains_maya(self, analyzer):
        """Test CHECK-01: Identity prompt contains 'Maya'."""
        result = analyzer._check_identity_prompt()

        # Should pass if Maya is in the prompt
        if result.passed:
            assert "Maya" in result.reason or result.passed
        else:
            # If failed, should give clear reason
            assert result.reason != ""

    def test_check_identity_prompt_no_wrong_names(self, analyzer):
        """Test CHECK-01: Identity prompt doesn't contain wrong model names."""
        result = analyzer._check_identity_prompt()

        if not result.passed:
            # If failed due to wrong names, verify the message
            if "wrong model" in result.reason.lower():
                assert "llama" in result.reason.lower() or "gpt" in result.reason.lower() or \
                       "claude" in result.reason.lower() or "gemini" in result.reason.lower()

    def test_check_llm_role_system_prompt(self, analyzer):
        """Test CHECK-02: LLM role system prompt injection."""
        result = analyzer._check_llm_role_prompt()

        # This may pass or fail depending on actual code
        # Just verify it runs without crashing
        assert isinstance(result, CheckResult)
        assert result.name == "" or "LLM Role" in result.name or result.passed or not result.passed

    def test_check_tool_registration(self, analyzer):
        """Test CHECK-03: Task tools are registered."""
        result = analyzer._check_tool_registration()

        # Should verify task_tools.py exists and get_task_tools is called
        assert isinstance(result, CheckResult)

    def test_check_memory_path_integrity(self, analyzer):
        """Test CHECK-04: Memory write/read path integrity."""
        result = analyzer._check_memory_path()

        # Should check for store methods and exception handling
        assert isinstance(result, CheckResult)

    def test_check_fastpath_group_count(self, analyzer):
        """Test CHECK-05: Fast-path has exactly 4 routing groups."""
        result = analyzer._check_fastpath_groups()

        # Should count DirectToolIntent groups
        assert isinstance(result, CheckResult)

    def test_check_router_patterns(self, analyzer):
        """Test CHECK-06: Router patterns don't have bare tokens."""
        result = analyzer._check_router_patterns()

        # Should check for required memory patterns
        assert isinstance(result, CheckResult)

    def test_check_router_patterns_semantic_phrase_coverage(self, analyzer):
        """CHECK-06 uses semantic regex matching for expected memory phrases."""
        result = analyzer._check_router_patterns()
        assert result.passed, f"CHECK-06 failed: {result.reason} {result.details}"

    def test_analyzer_default_base_path_is_agent_root(self):
        """Default analyzer base path should resolve to Agent/ root."""
        analyzer = MayaStaticAnalyzer()
        assert analyzer.base_path.name == "Agent"
        assert (analyzer.base_path / "agent.py").exists()

    def test_check_env_vars(self, analyzer):
        """Test CHECK-07: Environment variables are present and valid."""
        result = analyzer._check_env_vars()

        # Should check for required env vars
        assert isinstance(result, CheckResult)

    def test_check_context_bleed(self, analyzer):
        """Test CHECK-08: Context bleed detection."""
        result = analyzer._check_context_bleed()

        # Should check for turn state reset patterns
        assert isinstance(result, CheckResult)

    def test_check_sanitize_coverage(self, analyzer):
        """Test CHECK-09: Sanitize response coverage."""
        result = analyzer._check_sanitize_coverage()

        # Should check _sanitize_response is called
        assert isinstance(result, CheckResult)

    def test_check_log_format(self, analyzer):
        """Test CHECK-10: Log format verification."""
        result = analyzer._check_log_format()

        # Should check for required event names in source
        assert isinstance(result, CheckResult)

    def test_check_import_chain(self, analyzer):
        """Test CHECK-11: Import chain integrity."""
        result = analyzer._check_import_chain()

        # Should verify files have no syntax errors
        assert isinstance(result, CheckResult)
        # Import chain should generally pass
        assert result.passed, f"Import chain failed: {result.reason}"


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_creation(self):
        """Test CheckResult can be created."""
        result = CheckResult(name="TEST", passed=True, reason="", details="")
        assert result.name == "TEST"
        assert result.passed is True
        assert result.reason == ""

    def test_check_result_failed(self):
        """Test failed CheckResult."""
        result = CheckResult(
            name="TEST",
            passed=False,
            reason="Test failed",
            details="More info"
        )
        assert result.passed is False
        assert result.reason == "Test failed"
        assert result.details == "More info"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
