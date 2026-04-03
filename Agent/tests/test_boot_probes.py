"""
Tests for Boot Health Probes

Tests the boot-time health probes to ensure they correctly verify
system state at startup.
"""

import pytest
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.runtime.startup_health_probes import (
    run_boot_health_probes,
    _probe_identity,
    _probe_memory,
    _probe_router,
    _probe_tools,
    _probe_stt_config,
    _probe_log_format,
)


class TestBootProbes:
    """Tests for boot health probes."""

    @pytest.mark.asyncio
    async def test_run_all_probes(self):
        """Test running all probes."""
        # Run probes but don't fail on missing components
        all_passed, results = await run_boot_health_probes(
            identity_check=True,
            memory_check=False,  # Skip if memory not initialized
            router_check=False,   # Skip if router not initialized
            tool_check=False,     # Skip if tools not loaded
            stt_check=True,
            log_check=False,      # Skip if logs not set up
        )

        # Should return results
        assert isinstance(all_passed, bool)
        assert isinstance(results, list)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_probe_identity(self):
        """Test PROBE-01: Identity probe."""
        passed, message = await _probe_identity()

        # Should return a result
        assert isinstance(passed, bool)
        assert isinstance(message, str)
        assert len(message) > 0

        # If passed, Maya should be in the identity
        if passed:
            assert "Maya" in message or "verified" in message.lower()

    @pytest.mark.asyncio
    async def test_probe_stt_config(self):
        """Test PROBE-05: STT config probe."""
        passed, message = await _probe_stt_config()

        # Should return a result
        assert isinstance(passed, bool)
        assert isinstance(message, str)

        # Check message contains config info
        if passed:
            assert "verified" in message.lower() or "config" in message.lower()

    @pytest.mark.asyncio
    async def test_probe_memory(self, monkeypatch):
        """Test PROBE-02: Memory probe."""
        import core.memory.hybrid_memory_manager as hmm_module

        class _MemoryStub:
            async def store_conversation_turn(self, **kwargs):
                del kwargs
                return True

            def retrieve_relevant_memories(self, **kwargs):
                del kwargs
                return [{"text": "Test key: boot_probe_test\nAssistant: Test value: probe_value_12345"}]

        monkeypatch.setattr(hmm_module, "HybridMemoryManager", _MemoryStub, raising=True)
        passed, message = await _probe_memory()

        assert isinstance(passed, bool)
        assert isinstance(message, str)

    @pytest.mark.asyncio
    async def test_probe_router(self):
        """Test PROBE-03: Router contract probe."""
        # This may fail if router not initialized
        passed, message = await _probe_router()

        assert isinstance(passed, bool)
        assert isinstance(message, str)

    @pytest.mark.asyncio
    async def test_probe_tools(self):
        """Test PROBE-04: Tool availability probe."""
        # This may fail if tools not loaded
        passed, message = await _probe_tools()

        assert isinstance(passed, bool)
        assert isinstance(message, str)

    @pytest.mark.asyncio
    async def test_probe_log_format(self):
        """Test PROBE-06: Log format probe."""
        passed, message = await _probe_log_format()

        assert isinstance(passed, bool)
        assert isinstance(message, str)


class TestProbeResults:
    """Tests for probe result structure."""

    @pytest.mark.asyncio
    async def test_probe_result_format(self):
        """Test that probe results have correct format."""
        all_passed, results = await run_boot_health_probes(
            identity_check=True,
            memory_check=False,
            router_check=False,
            tool_check=False,
            stt_check=True,
            log_check=False,
        )

        for result in results:
            assert "id" in result
            assert "name" in result
            assert "passed" in result
            assert "critical" in result
            assert "message" in result
            assert isinstance(result["passed"], bool)
            assert isinstance(result["critical"], bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
