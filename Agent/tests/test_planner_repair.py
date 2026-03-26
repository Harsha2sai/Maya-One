import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from core.tasks.planner_schema_validator import TaskPlan
from core.tasks.planning_engine import PlanningEngine
from core.tasks.task_steps import TaskStep


@pytest.mark.asyncio
async def test_generate_plan_result_valid_taskplan_returns_steps():
    engine = PlanningEngine(smart_llm=MagicMock())
    engine._run_planner_prompt = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "title": "Reminder",
                    "description": "Set reminder",
                    "steps": [
                        {
                            "description": "Set reminder at 9pm",
                            "worker": "general",
                            "tool": "set_reminder",
                            "parameters": {"time": "9:00 PM", "text": "Call dad"},
                        }
                    ],
                }
            ),
            [],
        )
    )

    result = await engine.generate_plan_result("Set a reminder for 9pm to call dad")

    assert result.plan_failed is False
    assert len(result.steps) == 1
    assert result.steps[0].description == "Set reminder at 9pm"
    assert result.steps[0].tool == "set_reminder"


@pytest.mark.asyncio
async def test_generate_plan_result_uses_deterministic_multistep_reminder_plan():
    engine = PlanningEngine(smart_llm=MagicMock())

    result = await engine.generate_plan_result(
        "Set a reminder to check my email in 30 minutes and then open Chrome."
    )

    assert result.plan_failed is False
    assert len(result.steps) == 2
    assert result.steps[0].tool == "set_reminder"
    assert result.steps[1].tool == "open_app"
    payload = json.loads(result.raw_response)
    assert payload["steps"][0]["tool"] == "set_reminder"
    assert payload["steps"][1]["tool"] == "open_app"
    assert payload["steps"][0]["parameters"] == {"text": "check my email", "time": "in 30 minutes"}


@pytest.mark.asyncio
async def test_generate_plan_result_uses_deterministic_multistep_reminder_plan_without_then():
    engine = PlanningEngine(smart_llm=MagicMock())

    result = await engine.generate_plan_result(
        "Set a reminder to check email in 10 minutes and open Chrome"
    )

    assert result.plan_failed is False
    assert len(result.steps) == 2
    assert result.steps[0].worker == "general"
    assert result.steps[1].worker == "system"
    assert result.steps[1].tool == "open_app"


@pytest.mark.asyncio
async def test_generate_plan_result_repair_prompt_runs_after_validation_failure():
    engine = PlanningEngine(smart_llm=MagicMock())
    engine._run_planner_prompt = AsyncMock(
        side_effect=[
            ("{not json", []),
            (
                json.dumps(
                    {
                        "steps": [
                            {
                                "description": "Recovered step",
                                "worker": "general",
                            }
                        ]
                    }
                ),
                [],
            ),
        ]
    )

    result = await engine.generate_plan_result("Do something")

    assert result.plan_failed is False
    assert len(result.steps) == 1
    assert result.steps[0].description == "Recovered step"
    assert engine._run_planner_prompt.await_count == 2
    repair_prompt = engine._run_planner_prompt.await_args_list[1].args[0]
    assert "Repair the planner JSON" in repair_prompt
    assert "Schema:" in repair_prompt


@pytest.mark.asyncio
async def test_generate_plan_result_stops_after_two_repairs_and_plan_fails():
    engine = PlanningEngine(smart_llm=MagicMock())
    engine._run_planner_prompt = AsyncMock(
        side_effect=[
            ("{bad json", []),
            ("still bad", []),
            ("still invalid", []),
        ]
    )

    result = await engine.generate_plan_result("Broken request")

    assert result.plan_failed is True
    assert result.error_payload is not None
    assert result.error_payload["code"] == "PLANNER_VALIDATION_FAILED"
    assert result.error_payload["attempt_count"] == 2
    assert engine._run_planner_prompt.await_count == 3


@pytest.mark.asyncio
async def test_generate_plan_result_plan_failed_contains_structured_fallback_error():
    engine = PlanningEngine(smart_llm=MagicMock())
    engine._run_planner_prompt = AsyncMock(
        side_effect=[
            ("{bad json", []),
            ("still bad", []),
            ("still invalid", []),
        ]
    )

    result = await engine.generate_plan_result("Invalid planning output")

    assert result.plan_failed is True
    assert result.steps
    planner_error = result.steps[0].metadata.get("planner_error")
    assert planner_error is not None
    assert planner_error["code"] == "PLANNER_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_generate_plan_result_uses_tool_steps_when_no_json_content():
    engine = PlanningEngine(smart_llm=MagicMock())
    tool_steps = [
        TaskStep(description="Execute fallback", worker="general", tool=None, parameters={})
    ]
    engine._run_planner_prompt = AsyncMock(return_value=("", tool_steps))

    result = await engine.generate_plan_result("do it")

    assert result.plan_failed is False
    assert result.steps == tool_steps


@pytest.mark.asyncio
async def test_generate_plan_result_sanitizes_task_management_tool_from_taskplan():
    engine = PlanningEngine(smart_llm=MagicMock())
    engine._run_planner_prompt = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "steps": [
                        {
                            "description": "Create a nested task",
                            "worker": "general",
                            "tool": "create_task",
                            "parameters": {"description": "nested"},
                        }
                    ]
                }
            ),
            [],
        )
    )

    result = await engine.generate_plan_result("Create task")

    assert result.plan_failed is False
    assert len(result.steps) == 1
    assert result.steps[0].tool is None


@pytest.mark.asyncio
async def test_generate_plan_wrapper_returns_only_step_list():
    engine = PlanningEngine(smart_llm=MagicMock())
    engine.generate_plan_result = AsyncMock(
        return_value=SimpleNamespace(
            steps=[TaskStep(description="one", worker="general")],
            plan_failed=False,
            error_payload=None,
        )
    )

    steps = await engine.generate_plan("request")

    assert isinstance(steps, list)
    assert len(steps) == 1
    assert steps[0].description == "one"


def test_taskplan_schema_is_canonical_and_enforced():
    with pytest.raises(ValidationError):
        TaskPlan.model_validate({"title": "Missing steps"})

    valid = TaskPlan.model_validate(
        {
            "title": "Test",
            "steps": [{"description": "Step 1", "worker": "general"}],
        }
    )
    assert len(valid.steps) == 1
