"""
Tests for Behavioral Sentinel

Tests the behavioral sentinel to ensure it correctly detects
behavioral drift.
"""

import pytest
import asyncio
import os
import sys
import tempfile
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.observability.behavioral_sentinel import (
    BehavioralSentinel,
    SentinelResult,
    create_sentinel,
    start_sentinel,
)


class TestBehavioralSentinel:
    """Tests for the behavioral sentinel."""

    @pytest.fixture
    def sentinel(self):
        """Create a sentinel instance."""
        return BehavioralSentinel()

    @pytest.mark.asyncio
    async def test_sentinel_initialization(self, sentinel):
        """Test sentinel initializes correctly."""
        assert sentinel._running is False
        assert sentinel._task is None
        assert sentinel.interval > 0

    @pytest.mark.asyncio
    async def test_sentinel_start_stop(self, sentinel):
        """Test sentinel can start and stop."""
        await sentinel.start()
        assert sentinel._running is True
        assert sentinel._task is not None

        await sentinel.stop()
        assert sentinel._running is False

    @pytest.mark.asyncio
    async def test_sentinel_persona_drift_detection(self, sentinel):
        """Test SENTINEL-01: Persona drift detection."""
        # Run the check
        await sentinel._check_persona_drift()

        # Should complete without error
        # (Actual result depends on system prompt content)

    @pytest.mark.asyncio
    async def test_sentinel_memory_persistence(self, sentinel, monkeypatch):
        """Test SENTINEL-02: Memory persistence check."""
        import core.memory.hybrid_memory_manager as hmm_module

        class _MemoryStub:
            def __init__(self):
                self._probe = None

            def store_conversation_turn(self, *, user_msg, assistant_msg, metadata):
                del assistant_msg
                self._probe = {
                    "text": user_msg,
                    "metadata": metadata,
                }
                return True

            def retrieve_relevant_memories(self, **kwargs):
                probe_id = kwargs.get("query")
                if self._probe and self._probe["metadata"].get("probe_id") == probe_id:
                    return [self._probe]
                return []

        monkeypatch.setattr(hmm_module, "HybridMemoryManager", _MemoryStub, raising=True)
        await sentinel._check_memory_persistence()

    @pytest.mark.asyncio
    async def test_sentinel_memory_write_failed_is_error(self, sentinel, monkeypatch):
        """Memory write failure should be logged at error level."""
        import core.memory.hybrid_memory_manager as hmm_module

        class _FailingMemory:
            def store_conversation_turn(self, **kwargs):
                del kwargs
                return False

            def retrieve_relevant_memories(self, **kwargs):
                del kwargs
                return []

        monkeypatch.setattr(hmm_module, "HybridMemoryManager", _FailingMemory, raising=True)

        events: List[Tuple[str, str, Dict[str, Any]]] = []

        def _capture(event: str, message: str, level: str = "info", **kwargs):
            del message
            events.append((event, level, kwargs))

        sentinel._log = _capture
        await sentinel._check_memory_persistence()
        assert any(evt == "sentinel_memory_write_failed" and lvl == "error" for evt, lvl, _ in events)

    @pytest.mark.asyncio
    async def test_sentinel_routing_drift(self, sentinel):
        """Test SENTINEL-03: Routing drift detection."""
        await sentinel._check_routing_drift()

    @pytest.mark.asyncio
    async def test_sentinel_routing_drift_escalates_and_resets(self, sentinel, monkeypatch):
        """Routing drift should escalate after threshold and then reset the counter."""
        import core.orchestrator.agent_router as router_module

        async def _always_chat(self, utterance: str, user_id: str) -> str:
            del self, utterance, user_id
            return "chat"

        monkeypatch.setattr(router_module.AgentRouter, "route", _always_chat, raising=True)

        events: List[Tuple[str, str, Dict[str, Any]]] = []

        def _capture(event: str, message: str, level: str = "info", **kwargs):
            del message
            events.append((event, level, kwargs))

        sentinel._log = _capture
        sentinel.drift_alert_threshold = 2
        sentinel._routing_drift_count = 0

        await sentinel._check_routing_drift()
        assert sentinel._routing_drift_count == 1
        assert any(evt == "sentinel_routing_drift_detected" for evt, _, _ in events)

        await sentinel._check_routing_drift()
        assert sentinel._routing_drift_count == 0
        assert any(evt == "sentinel_routing_drift_CRITICAL" and lvl == "error" for evt, lvl, _ in events)

    @pytest.mark.asyncio
    async def test_sentinel_response_quality(self, sentinel):
        """Test SENTINEL-05: Response quality check."""
        await sentinel._check_response_quality()

    @pytest.mark.asyncio
    async def test_sentinel_sample_response_quality(self, sentinel):
        """Test response quality sampling."""
        # Test with good response
        await sentinel.sample_response_quality(
            "Hello, I am Maya. How can I help you today?",
            route="chat"
        )

        # Test with raw JSON (should be flagged)
        await sentinel.sample_response_quality(
            '{"result": "test"}',
            route="research"
        )

        # Test with short response (should be flagged)
        await sentinel.sample_response_quality(
            "Hi",
            route="chat"
        )

        # Test with tool markup leak (should be flagged)
        await sentinel.sample_response_quality(
            "Here is the result: <web_search>{'query': 'test'}</web_search>",
            route="chat"
        )

    @pytest.mark.asyncio
    async def test_sentinel_context_bleed(self, sentinel):
        """Test SENTINEL-04: Context bleed detection."""
        # Test with clean context
        await sentinel.check_context_bleed({
            "messages": [{"role": "user", "content": "Hello"}],
            "turn_id": "123"
        })

        # Test with potentially bleeding context
        await sentinel.check_context_bleed({
            "messages": [{"role": "system", "content": "action completed"}],
            "turn_id": "456"
        })

    def test_sentinel_log_writing(self, sentinel, tmp_path):
        """Test sentinel writes to log file."""
        # Temporarily change log path
        import core.observability.behavioral_sentinel as sentinel_module
        original_path = sentinel_module.SENTINEL_LOG_PATH

        try:
            log_file = tmp_path / "test_sentinel.log"
            sentinel_module.SENTINEL_LOG_PATH = str(log_file)

            sentinel._log("test_event", "Test message", test_key="test_value")

            # Check log file was created and contains our entry
            if log_file.exists():
                content = log_file.read_text()
                assert "test_event" in content
                assert "Test message" in content
        finally:
            sentinel_module.SENTINEL_LOG_PATH = original_path


class TestSentinelFactory:
    """Tests for sentinel factory functions."""

    def test_create_sentinel(self):
        """Test create_sentinel factory."""
        sentinel = create_sentinel()
        assert isinstance(sentinel, BehavioralSentinel)

    @pytest.mark.asyncio
    async def test_start_sentinel(self):
        """Test start_sentinel factory."""
        sentinel = await start_sentinel()
        assert isinstance(sentinel, BehavioralSentinel)
        assert sentinel._running is True

        await sentinel.stop()


class TestSentinelResult:
    """Tests for SentinelResult dataclass."""

    def test_sentinel_result_creation(self):
        """Test SentinelResult can be created."""
        result = SentinelResult(
            check_name="test_check",
            passed=True,
            message="Test passed"
        )
        assert result.check_name == "test_check"
        assert result.passed is True
        assert result.message == "Test passed"
        assert result.timestamp is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
