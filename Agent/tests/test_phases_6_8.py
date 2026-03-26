"""
Test Phases 6-8 Components
"""
import pytest

# Phase 6: Multi-Agent Tests
@pytest.mark.asyncio
async def test_agent_registry():
    """Test specialized agent registration and routing"""
    from core.agents.base import AgentContext, SpecializedAgent
    from core.agents.registry import AgentRegistry
    from core.response.agent_response import AgentResponse

    class _FakeResearchAgent(SpecializedAgent):
        def __init__(self):
            super().__init__("fake_research")

        async def can_handle(self, request: str, context: AgentContext) -> float:
            del context
            return 0.9 if "python" in request.lower() else 0.0

        async def execute(self, request: str, context: AgentContext) -> AgentResponse:
            del request, context
            return AgentResponse(
                display_text="Python is a programming language.",
                voice_text="Python is a programming language.",
                mode="normal",
                confidence=0.9,
            )

    registry = AgentRegistry()
    registry.agents = [_FakeResearchAgent()]
    
    context = AgentContext(
        user_id="test",
        user_role="admin",
        conversation_history=[],
        memory_context=""
    )
    
    response = await registry.execute("What is Python?", context)
    # AgentResponse contract: display/voice fields (no legacy success/content fields).
    assert bool(getattr(response, "display_text", "").strip())
    assert getattr(response, "confidence", 0.0) >= 0.0
    print(f"✅ Agent routing: {response.display_text[:50]}")

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
