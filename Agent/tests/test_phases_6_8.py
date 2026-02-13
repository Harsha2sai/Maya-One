"""
Test Phases 6-8 Components
"""
import pytest
import asyncio

# Phase 6: Multi-Agent Tests
@pytest.mark.asyncio
async def test_agent_registry():
    """Test specialized agent registration and routing"""
    from core.agents.registry import get_agent_registry
    from core.agents.base import AgentContext
    
    registry = get_agent_registry()
    
    # Test research agent
    context = AgentContext(
        user_id="test",
        user_role="admin",
        conversation_history=[],
        memory_context=""
    )
    
    response = await registry.execute("What is Python?", context)
    assert response.success or response.requires_handoff
    print(f"✅ Agent routing: {response.content[:50]}")

# Phase 7: Skill Registry Tests
def test_skill_registration():
    """Test skill package loading"""
    from core.skills.registry import get_skill_registry
    from core.governance.types import UserRole
    from pathlib import Path
    
    registry = get_skill_registry()
    
    # Load example weather skill
    skill_path = Path("skills/weather_skill.py")
    if skill_path.exists():
        success = registry.load_from_file(skill_path, UserRole.ADMIN)
        assert success
        print("✅ Skill loaded successfully")
    
    skills = registry.list_skills()
    print(f"✅ Total skills loaded: {len(skills)}")

# Phase 8: Cognition Tests
@pytest.mark.asyncio
async def test_self_reflection():
    """Test self-reflection engine"""
    from core.cognition.reflection import reflection_engine
    
    result = await reflection_engine.reflect_on_action(
        action="delete all files",
        context={},
        tool_name="delete_file"
    )
    
    assert len(result.concerns) > 0  # Should flag risky operation
    print(f"✅ Reflection detected concerns: {result.concerns}")

def test_strategy_validation():
    """Test strategy validator"""
    from core.cognition.validator import strategy_validator
    
    plan = [
        {"description": "Step 1", "tool": "tool_a"},
        {"description": "Step 2", "tool": "tool_b"}
    ]
    
    result = strategy_validator.validate_plan("Test goal", plan)
    assert result.score > 0
    print(f"✅ Plan validation score: {result.score:.2f}")

def test_outcome_learning():
    """Test outcome-based learning"""
    from core.cognition.learning import outcome_learner
    
    outcome_learner.record_outcome(
        action="test_action",
        tool_name="test_tool",
        success=True,
        context={"test": "data"}
    )
    
    success_rate = outcome_learner.get_success_rate("test_tool")
    print(f"✅ Recorded outcome, success rate: {success_rate:.1%}")
