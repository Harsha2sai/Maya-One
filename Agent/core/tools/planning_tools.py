
import logging
import json
from typing import List, Dict, Any
from core.registry.tool_registry import ToolRegistry, ToolMetadata
from core.intelligence.planner import task_planner

logger = logging.getLogger(__name__)

async def define_plan(goal: str, steps_json: str) -> str:
    """
    Define a multi-step plan for a complex goal.
    Steps should be a JSON array of objects: [{"description": "...", "tool_name": "...", "parameters": {...}}]
    """
    try:
        steps = json.loads(steps_json)
        task_planner.create_plan(goal, steps)
        return f"Plan defined for: {goal}. I will now begin executing the first step: {steps[0]['description']}"
    except Exception as e:
        logger.error(f"❌ Failed to define plan: {e}")
        return f"Error creating plan: {str(e)}"

def register_planning_tool(registry: ToolRegistry):
    """Register the planning tool."""
    registry.register_tool(ToolMetadata(
        name="define_plan",
        description="Breaks a complex goal into sequential steps. Use this for multi-step tasks.",
        parameters={
            "goal": {"type": "string", "description": "The overall objective"},
            "steps_json": {"type": "string", "description": "JSON array of steps with description, tool_name, and parameters"}
        },
        required_params=["goal", "steps_json"],
        category="intelligence"
    ), define_plan)
