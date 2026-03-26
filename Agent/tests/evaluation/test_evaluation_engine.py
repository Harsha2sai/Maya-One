"""
Tests for the evaluation engine and evaluators.

Validates that the evaluation layer correctly detects runtime regressions.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path

from core.evaluation.evaluation_engine import EvaluationEngine, SystemStats
from core.evaluation.evaluators.memory_evaluator import validate_memory_schema
from telemetry.session_monitor import RequestMetrics


def test_high_latency_fails_health():
    """High latency should trigger health failure"""
    engine = EvaluationEngine()
    
    # Simulate high latency (above 3.0s threshold)
    metrics = RequestMetrics(
        stream_first_chunk_latency=5.7,  # Above threshold
        tokens_in=1500,
        llm_latency=6.0
    )
    
    health = engine.evaluate(metrics)
    
    assert not health.llm_latency_ok, "High latency should fail LLM health check"
    assert health.overall_score < 1.0, "Overall score should be degraded"


def test_high_token_count_fails_health():
    """High token count should trigger health failure"""
    engine = EvaluationEngine()
    
    # Simulate high token count (above 2000 threshold)
    metrics = RequestMetrics(
        stream_first_chunk_latency=2.0,
        tokens_in=2600,  # Above threshold
        llm_latency=2.5
    )
    
    health = engine.evaluate(metrics)
    
    assert not health.llm_latency_ok, "High token count should fail LLM health check"
    assert health.overall_score < 1.0


def test_high_memory_fails_health():
    """High memory usage should trigger health failure"""
    engine = EvaluationEngine()
    
    # Simulate high memory (above 2000MB threshold)
    stats = SystemStats(memory_mb=2500)
    
    health = engine.evaluate(None, stats)
    
    assert not health.stability_ok, "High memory should fail stability check"
    assert health.overall_score < 1.0


def test_provider_failures_fail_health():
    """Provider failures should trigger health failure"""
    engine = EvaluationEngine()
    
    # Simulate provider failures
    metrics = RequestMetrics(
        probe_failures=1,
        retry_count=3
    )
    
    health = engine.evaluate(metrics)
    
    assert not health.providers_ok, "Provider failures should fail provider health check"
    assert health.overall_score < 1.0


def test_schema_validation_catches_missing_column():
    """Schema validator should catch missing user_id column"""
    # Create temporary database with old schema (no user_id)
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE VIRTUAL TABLE memory_fts USING fts5(
                id UNINDEXED,
                text,
                source,
                metadata UNINDEXED,
                created_at UNINDEXED
            )
        """)
        conn.close()
        
        # Validation should fail (missing user_id)
        assert not validate_memory_schema(db_path), "Should detect missing user_id column"
    finally:
        Path(db_path).unlink()


def test_schema_validation_passes_with_correct_schema():
    """Schema validator should pass with correct schema"""
    # Create temporary database with correct schema
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE VIRTUAL TABLE memory_fts USING fts5(
                id UNINDEXED,
                user_id UNINDEXED,
                text,
                source,
                metadata UNINDEXED,
                created_at UNINDEXED
            )
        """)
        conn.close()
        
        # Validation should pass
        assert validate_memory_schema(db_path), "Should validate correct schema"
    finally:
        Path(db_path).unlink()


def test_healthy_system_passes_all_checks():
    """Healthy system should pass all checks"""
    engine = EvaluationEngine()
    
    # Simulate healthy metrics
    metrics = RequestMetrics(
        stream_first_chunk_latency=2.0,  # Below 3.0s
        tokens_in=1500,  # Below 2000
        llm_latency=2.5,
        probe_failures=0,
        retry_count=0
    )
    
    stats = SystemStats(memory_mb=1200)  # Below 2000MB
    
    health = engine.evaluate(metrics, stats)
    
    assert health.llm_latency_ok
    assert health.memory_ok
    assert health.providers_ok
    assert health.tools_ok
    assert health.stability_ok
    assert health.overall_score == 1.0
    assert health.is_healthy()


def test_overall_score_computation():
    """Overall score should be computed correctly"""
    engine = EvaluationEngine()
    
    # 3 out of 5 checks pass
    metrics = RequestMetrics(
        stream_first_chunk_latency=5.0,  # FAIL
        tokens_in=1500,  # PASS
        probe_failures=1,  # FAIL
        retry_count=0
    )
    
    stats = SystemStats(memory_mb=1200)  # PASS
    
    health = engine.evaluate(metrics, stats)
    
    # LLM: FAIL, Memory: PASS, Provider: FAIL, Tool: PASS, Stability: PASS
    # Score should be 3/5 = 0.6
    assert health.overall_score == 0.6
    assert not health.is_healthy()  # Below 0.8 threshold
