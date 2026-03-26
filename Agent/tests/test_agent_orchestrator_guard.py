
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from core.orchestrator.agent_orchestrator import AgentOrchestrator

@pytest.fixture
def mock_deps():
    with patch("core.orchestrator.agent_orchestrator.PlanningEngine") as MockPlanner, \
         patch("core.orchestrator.agent_orchestrator.TaskStore") as MockStore:
        
        # Setup Planner mock
        planner = MockPlanner.return_value
        planner.generate_plan = AsyncMock()
        
        # Setup Store mock
        store = MockStore.return_value
        store.create_task = AsyncMock(return_value=True)
        
        yield planner, store

@pytest.mark.asyncio
async def test_handle_intent_rejection(mock_deps):
    mock_planner, mock_store = mock_deps
    
    # Mock Guard
    mock_guard = MagicMock()
    # Simulate high token count
    mock_guard.count_tokens.return_value = 5000 
    
    orchestrator = AgentOrchestrator(
        MagicMock(), 
        MagicMock(), 
        context_guard=mock_guard
    )
    orchestrator.agent.smart_llm = None
    orchestrator._ensure_task_worker = AsyncMock()
    # Patched method to capturing announce
    orchestrator._announce = AsyncMock() 

    response = await orchestrator.handle_message("Huge request", user_id="test_user")
    
    assert "too long" in response.display_text
    mock_planner.generate_plan.assert_not_called()
    mock_store.create_task.assert_not_called()
    orchestrator._announce.assert_called_once()

@pytest.mark.asyncio
async def test_handle_intent_acceptance(mock_deps):
    mock_planner, mock_store = mock_deps
    
    # Mock Guard
    mock_guard = MagicMock()
    # Simulate low token count
    mock_guard.count_tokens.return_value = 100
    
    orchestrator = AgentOrchestrator(
        MagicMock(), 
        MagicMock(), 
        context_guard=mock_guard
    )
    orchestrator.agent.smart_llm = None
    orchestrator._announce = AsyncMock() 

    # Plan returns something so we don't fail later
    mock_planner.generate_plan.return_value = []
    
    await orchestrator.handle_message("Create task: small request", user_id="test_user")
    
    mock_planner.generate_plan.assert_called_once()
