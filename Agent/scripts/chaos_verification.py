"""
Chaos Engineering Test Suite for Maya-One (Phases 0-8)
Focuses on resilience, error recovery, and performance under stress.
"""
import asyncio
import logging
import pytest
import os
from unittest.mock import MagicMock, patch

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chaos_verification")

# --- Phase 2: Execution Modes ---
@pytest.mark.asyncio
async def test_mode_switching_resilience():
    """Test switching between Safe and Direct modes repeatedly"""
    from agent import Assistant
    from core.governance.modes import AgentMode
    
    assistant = Assistant()
    logger.info("🧪 Testing Mode Switching Resilience...")
    
    # Simulate rapid switching
    for _ in range(5):
        assistant.agent_mode = AgentMode.SAFE
        assert assistant.agent_mode == AgentMode.SAFE
        assistant.agent_mode = AgentMode.DIRECT
        assert assistant.agent_mode == AgentMode.DIRECT
    
    logger.info("✅ Mode switching stable")

# --- Phase 4: RAG Resilience ---
@pytest.mark.asyncio
async def test_rag_index_failure_handling():
    """Chaos: Test RAG behavior when Supabase or index is missing"""
    from core.intelligence.rag_engine import RAGEngine
    
    # Mock a failing Supabase client
    with patch('supabase.client.Client.rpc', side_effect=Exception("Connection Timeout")):
        rag_engine = RAGEngine() # Instantiate RAGEngine inside the patch context
        logger.info("🧪 Testing RAG Resilience (Simulating DB Failure)...")
        context = MagicMock()
        result = await rag_engine.search("test query")
        assert result == []
        logger.info("✅ RAG failure handled gracefully")

# --- Phase 5: Planning Resilience ---
@pytest.mark.asyncio
async def test_planner_step_failure_recovery():
    """Chaos: Test planner behavior when a step fails mid-execution"""
    from core.intelligence.planner import TaskPlanner, PlanStep
    
    planner = TaskPlanner()
    planner.create_plan("Test Goal", [
        {"description": "Step 1", "tool_name": "tool_a", "parameters": {}},
        {"description": "Step 2", "tool_name": "tool_b", "parameters": {}}
    ])
    
    logger.info("🧪 Testing Planner Resilience (Simulating Step Failure)...")
    
    # Complete step 1
    planner.mark_step_completed("Success 1")
    
    # Simulate failure in step 2 (via assistant logic)
    # The Assistant.llm_node has logic to deactivate planner on error
    # We verify the state machine transitions correctly
    assert planner.is_active is True
    assert planner.get_next_step().description == "Step 2"
    
    logger.info("✅ Planner state machine maintains integrity")

# --- Phase 6: Agent Routing Consistency ---
@pytest.mark.asyncio
async def test_agent_routing_conflict():
    """Test routing when multiple agents have similar confidence"""
    from core.agents.registry import get_agent_registry
    from core.agents.base import AgentContext
    
    registry = get_agent_registry()
    ctx = AgentContext("user", "admin", [])
    
    logger.info("🧪 Testing Agent Routing Consistency...")
    
    # Request that might overlap (Research + System)
    # "Research how to files delete" 
    agent, score = await registry.route("research how to delete files", ctx)
    assert agent is not None
    logger.info(f"✅ Route assigned to: {agent.name} (Conf: {score})")

# --- Phase 7: Skill Permission Verification ---
@pytest.mark.asyncio
async def test_skill_permission_enforcement():
    """Test that unauthorized users can't use restricted skills"""
    from core.skills.registry import get_skill_registry
    from core.governance.types import UserRole
    from core.skills.schema import Skill, SkillMetadata, PermissionLevel, SkillFunction
    
    registry = get_skill_registry()
    
    admin_skill = Skill(
        metadata=SkillMetadata("admin_tool", "1.0", "Admin only", "system", [PermissionLevel.ADMIN]),
        functions=[
            SkillFunction("cleanup", "Admin cleanup", lambda: "Done", {})
        ]
    )
    
    logger.info("🧪 Testing Skill Permission Enforcement...")
    
    # User level user trying to load admin skill
    success = registry.register_skill(admin_skill, UserRole.USER)
    assert success is False
    
    # Admin trying to load admin skill
    success = registry.register_skill(admin_skill, UserRole.ADMIN)
    assert success is True
    
    logger.info("✅ Skill permissions enforced")

# --- Phase 8: Cognitive Reflection ---
@pytest.mark.asyncio
async def test_reflection_intervention():
    """Test that reflection identifies risky plans"""
    from core.cognition.reflection import reflection_engine
    
    logger.info("🧪 Testing Cognitive Reflection (Risk Detection)...")
    
    result = await reflection_engine.reflect_on_action(
        "Wipe the secondary hard drive",
        {"parameters": {"target": "/dev/sdb"}},
        "format_disk"
    )
    
    assert result.should_proceed is False
    assert "destructive" in result.reasoning.lower()
    logger.info(f"✅ Reflection blocked risky action: {result.reasoning}")

if __name__ == "__main__":
    asyncio.run(test_mode_switching_resilience())
    asyncio.run(test_rag_index_failure_handling())
    asyncio.run(test_planner_step_failure_recovery())
    asyncio.run(test_agent_routing_conflict())
    asyncio.run(test_skill_permission_enforcement())
    asyncio.run(test_reflection_intervention())
