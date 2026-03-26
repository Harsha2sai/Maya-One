
import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from core.tasks.planning_engine import PlanningEngine

# Mock Chunk for streaming response
class MockChunk:
    def __init__(self, content):
        self.choices = [MagicMock(delta=MagicMock(content=content))]

@pytest.fixture
def mock_llm():
    with patch("core.tasks.planning_engine.ProviderFactory") as factory:
        mock_llm_instance = MagicMock()
        factory.get_llm.return_value = mock_llm_instance
        yield mock_llm_instance

@pytest.mark.asyncio
async def test_generate_plan_success(mock_llm):
    # Setup mock stream
    plan_json = {
        "title": "Test Plan",
        "description": "Testing",
        "steps": [
            {"description": "Step 1", "worker": "research", "tool": "web_search", "parameters": {"query": "test"}},
            {"description": "Step 2", "worker": "general"}
        ]
    }
    json_str = json.dumps(plan_json)
    
    # Async iterator for stream
    async def async_gen():
        yield MockChunk(json_str)
    
    mock_llm.chat.return_value = async_gen()
    
    engine = PlanningEngine()
    steps = await engine.generate_plan("Research something")
    
    assert len(steps) == 2
    assert steps[0].description == "Step 1"
    assert steps[0].worker == "research"
    assert steps[0].tool == "web_search"
    assert steps[0].parameters == {"query": "test"}
    assert steps[1].worker == "general"

@pytest.mark.asyncio
async def test_generate_plan_parsing_failure(mock_llm):
    # Async iterator returning garbage
    async def async_gen():
        yield MockChunk("NOT JSON")
    
    mock_llm.chat.return_value = async_gen()
    
    engine = PlanningEngine()
    steps = await engine.generate_plan("Do something")
    
    # Assert fallback behavior
    assert len(steps) == 1
    assert steps[0].worker == "general"
    assert "Do something" in steps[0].description
