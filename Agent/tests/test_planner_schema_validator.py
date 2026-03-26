
import pytest
import json
from core.tasks.planner_schema_validator import (
    PlannerSchemaValidator,
    PlannerResponse,
    PlannedStep,
    AllowedWorkerType,
    PlannerValidationCode,
)


@pytest.mark.phase4
class TestPlannerSchemaValidation:
    def test_valid_response(self):
        raw = {
            "title": "Test Plan",
            "description": "Testing",
            "steps": [
                {"description": "Step 1", "worker": "research", "tool": "search", "parameters": {"q": "test"}},
                {"description": "Step 2", "worker": "general"}
            ]
        }
        result = PlannerSchemaValidator.validate_response(raw)
        assert result is not None
        assert len(result.steps) == 2
        assert result.steps[0].worker == AllowedWorkerType.RESEARCH

    def test_invalid_response_missing_steps(self):
        raw = {"title": "Test Plan"}
        result = PlannerSchemaValidator.validate_response(raw)
        assert result is None

    def test_invalid_response_empty_description(self):
        raw = {"steps": [{"description": ""}]}
        result = PlannerSchemaValidator.validate_response(raw)
        assert result is None

    def test_response_with_too_many_steps(self):
        raw = {"steps": [{"description": f"Step {i}"} for i in range(25)]}
        result = PlannerSchemaValidator.validate_response(raw)
        assert result is None


class TestPlannerRepairLayer:
    def test_repair_invalid_json(self):
        invalid_json = "This is not JSON {broken"
        result = PlannerSchemaValidator.repair_and_validate(invalid_json, repair_attempt=True)
        assert result is None

    def test_repair_with_smart_quotes(self):
        raw_json = '{"title": "Test", "steps": [{"description": "Step 1", "worker": "general"}]}'
        smart_quoted = raw_json.replace('"', '\u201c').replace('"', '\u201d')
        result = PlannerSchemaValidator.repair_and_validate(smart_quoted, repair_attempt=True)
        assert result is not None
        assert len(result.steps) == 1

    def test_repair_with_trailing_comma(self):
        raw_json = '{"title": "Test", "steps": [{"description": "Step 1", "worker": "general"},]}'
        result = PlannerSchemaValidator.repair_and_validate(raw_json, repair_attempt=True)
        assert result is not None

    def test_repair_missing_steps(self):
        raw_json = '{"title": "Test only"}'
        result = PlannerSchemaValidator.repair_and_validate(raw_json, repair_attempt=True)
        assert result is not None
        assert len(result.steps) >= 1

    def test_repair_string_step(self):
        raw_json = '{"steps": ["Step A", "Step B"]}'
        result = PlannerSchemaValidator.repair_and_validate(raw_json, repair_attempt=True)
        assert result is not None
        assert len(result.steps) == 2

    def test_fallback_to_single_step(self):
        garbage = "completely invalid response!!!"
        result = PlannerSchemaValidator.repair_and_validate(garbage, repair_attempt=True)
        assert result is None


class TestPlannerGuardrails:
    def test_enforce_max_steps(self):
        steps = [{"description": f"Step {i}"} for i in range(25)]
        raw_json = json.dumps({"steps": steps})
        validated = PlannerSchemaValidator.repair_and_validate(raw_json, repair_attempt=True)
        assert validated is not None
        enforced = PlannerSchemaValidator.enforce_guardrails(validated)
        assert len(enforced.steps) <= 20

    def test_enforce_valid_worker(self):
        raw_json = '{"steps": [{"description": "Step 1", "worker": "invalid_worker"}]}'
        validated = PlannerSchemaValidator.repair_and_validate(raw_json, repair_attempt=True)
        assert validated is not None
        enforced = PlannerSchemaValidator.enforce_guardrails(validated)
        assert enforced.steps[0].worker == AllowedWorkerType.GENERAL

    def test_validate_tool_permission_allowed(self):
        step = PlannedStep(description="Test", tool="web_search", worker=AllowedWorkerType.RESEARCH)
        allowed = ["web_search", "google_search", "browser_open"]
        assert PlannerSchemaValidator.validate_tool_permission(step, allowed) is True

    def test_validate_tool_permission_denied(self):
        step = PlannedStep(description="Test", tool="run_shell_command", worker=AllowedWorkerType.RESEARCH)
        allowed = ["web_search", "google_search"]
        assert PlannerSchemaValidator.validate_tool_permission(step, allowed) is False

    def test_repair_forbidden_tool(self):
        step = PlannedStep(description="Test", tool="run_shell_command", worker=AllowedWorkerType.RESEARCH)
        allowed = ["web_search"]
        repaired = PlannerSchemaValidator.repair_forbidden_tool(step, allowed)
        assert repaired.tool is None
        assert repaired.description == "Test"


class TestPlannerIntegration:
    def test_full_repair_pipeline(self):
        messy_json = '{"title": "Research Task", "steps": [{"description": "Search for info", "worker": "research"}, {"description": "Analyze results", "worker": "general", "tool": "invalid_tool_not_allowed"}]}'
        result = PlannerSchemaValidator.repair_and_validate(messy_json, repair_attempt=True)
        assert result is not None
        assert len(result.steps) == 2
        
        enforced = PlannerSchemaValidator.enforce_guardrails(result)
        assert enforced.steps[1].worker == AllowedWorkerType.GENERAL
        
        from core.tasks.workers.capabilities import get_allowed_tools
        from core.tasks.task_steps import WorkerType
        
        final_steps = []
        for step in enforced.steps:
            wt = step.worker.value
            worker_tools = get_allowed_tools(WorkerType(wt))
            repaired_step = PlannerSchemaValidator.repair_forbidden_tool(step, worker_tools)
            final_steps.append(repaired_step)
        
        assert final_steps[1].tool is None

    def test_missing_steps_returns_machine_readable_issue(self):
        result = PlannerSchemaValidator.validate_response_with_issues({"title": "No steps"})
        assert result.plan is None
        assert result.issues
        assert result.issues[0].code == PlannerValidationCode.MISSING_REQUIRED_FIELDS

    def test_invalid_step_order_returns_issue_code(self):
        raw = {
            "steps": [
                {"description": "Step 1", "worker": "general", "order": 1},
                {"description": "Step 2", "worker": "general", "order": 3},
            ]
        }
        result = PlannerSchemaValidator.validate_response_with_issues(raw)
        assert result.plan is None
        assert any(i.code == PlannerValidationCode.INVALID_STEP_ORDER for i in result.issues)

    def test_enforced_tool_permission_returns_forbidden_issue(self):
        raw = {
            "steps": [
                {
                    "description": "Use forbidden system tool",
                    "worker": "research",
                    "tool": "run_shell_command",
                    "parameters": {},
                }
            ]
        }
        result = PlannerSchemaValidator.validate_response_with_issues(raw, enforce_tool_permissions=True)
        assert result.plan is None
        assert any(i.code == PlannerValidationCode.FORBIDDEN_TOOL for i in result.issues)
