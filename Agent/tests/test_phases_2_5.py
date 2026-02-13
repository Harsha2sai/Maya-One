"""
Test Phase 2-5 Components
"""
import pytest
import asyncio
from datetime import datetime

# Phase 2: Memory Tests
@pytest.mark.asyncio
async def test_conversation_store():
    """Test conversation history storage."""
    from core.memory.conversation_store import ConversationStore
    
    store = ConversationStore()
    
    # Note: This requires Supabase to be configured
    # In production, use mocks for unit tests
    assert store.db is not None

@pytest.mark.asyncio
async def test_preference_manager():
    """Test user preference management."""
    from core.memory.preference_manager import PreferenceManager
    
    manager = PreferenceManager()
    assert manager.db is not None

# Phase 4: Performance Tests
def test_metrics_collector():
    """Test metrics collection."""
    from core.observability.metrics import MetricsCollector
    
    metrics = MetricsCollector()
    
    # Test counter
    metrics.increment("test_counter")
    assert metrics.counters["test_counter"] == 1
    
    # Test gauge
    metrics.set_gauge("test_gauge", 42.0)
    assert metrics.gauges["test_gauge"] == 42.0
    
    # Test histogram
    metrics.record_histogram("test_histogram", 1.5)
    stats = metrics.get_stats("test_histogram")
    assert stats["count"] == 1
    assert stats["avg"] == 1.5

def test_llm_cache():
    """Test LLM response caching."""
    from core.cache.llm_cache import LLMCache
    
    cache = LLMCache(ttl_seconds=60)
    
    messages = [{"role": "user", "content": "Hello"}]
    model = "test-model"
    response = "Hi there!"
    
    # Cache miss
    assert cache.get(messages, model) is None
    
    # Set cache
    cache.set(messages, model, response)
    
    # Cache hit
    assert cache.get(messages, model) == response
    
    # Check stats
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5

def test_tool_cache():
    """Test tool result caching."""
    from core.cache.tool_cache import ToolCache
    
    cache = ToolCache()
    
    tool_name = "get_weather"
    params = {"city": "London"}
    result = {"temp": 15, "condition": "cloudy"}
    
    # Cache miss
    assert cache.get(tool_name, params) is None
    
    # Set cache
    cache.set(tool_name, params, result)
    
    # Cache hit
    assert cache.get(tool_name, params) == result

# Phase 5: Security Tests
def test_input_sanitizer():
    """Test input sanitization."""
    from core.security.sanitizer import InputSanitizer
    
    sanitizer = InputSanitizer()
    
    # Test normal input
    clean = sanitizer.sanitize_string("Hello World")
    assert clean == "Hello World"
    
    # Test dangerous pattern
    with pytest.raises(ValueError):
        sanitizer.sanitize_string("<script>alert('xss')</script>")
    
    # Test length limit
    long_text = "a" * 20000
    clean = sanitizer.sanitize_string(long_text, max_length=1000)
    assert len(clean) == 1000
    
    # Test UUID validation
    assert sanitizer.validate_user_id("550e8400-e29b-41d4-a716-446655440000")
    assert not sanitizer.validate_user_id("invalid-uuid")

@pytest.mark.asyncio
async def test_task_scheduler():
    """Test background task scheduler."""
    from core.scheduler.task_scheduler import TaskScheduler
    
    scheduler = TaskScheduler()
    
    # Start scheduler
    await scheduler.start()
    assert scheduler.running is True
    
    # Stop scheduler
    await scheduler.stop()
    assert scheduler.running is False

def test_context_analyzer():
    """Test context analysis."""
    from core.intelligence.context_analyzer import ContextAnalyzer
    
    analyzer = ContextAnalyzer()
    assert analyzer.db is not None
