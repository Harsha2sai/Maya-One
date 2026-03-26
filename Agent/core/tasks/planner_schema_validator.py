import json
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from core.tasks.task_steps import WorkerType

logger = logging.getLogger(__name__)


class AllowedWorkerType(str, Enum):
    GENERAL = "general"
    RESEARCH = "research"
    AUTOMATION = "automation"
    SYSTEM = "system"

    @classmethod
    def from_string(cls, value: str) -> "AllowedWorkerType":
        normalized = str(value).strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.GENERAL


class TaskPlanStep(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    worker: AllowedWorkerType = Field(default=AllowedWorkerType.GENERAL)
    tool: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    order: Optional[int] = Field(default=None, ge=1)

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters(cls, v):
        if v is None:
            return {}
        if not isinstance(v, dict):
            return {}
        return v


class TaskPlan(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    steps: List[TaskPlanStep] = Field(..., min_length=1)

    @field_validator("steps")
    @classmethod
    def validate_steps_length(cls, v):
        if len(v) > 20:
            raise ValueError("Maximum 20 steps allowed")
        return v


# Backward compatibility for existing imports/tests.
PlannedStep = TaskPlanStep
PlannerResponse = TaskPlan


class PlannerValidationCode(str, Enum):
    MALFORMED_JSON = "MALFORMED_JSON"
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    FORBIDDEN_TOOL = "FORBIDDEN_TOOL"
    INVALID_STEP_ORDER = "INVALID_STEP_ORDER"
    EMPTY_PLAN = "EMPTY_PLAN"


class PlannerValidationIssue(BaseModel):
    code: PlannerValidationCode
    message: str
    step_index: Optional[int] = None


class PlannerValidationResult(BaseModel):
    plan: Optional[TaskPlan] = None
    issues: List[PlannerValidationIssue] = Field(default_factory=list)
    repaired: bool = False
    attempt_count: int = 0


class PlannerSchemaValidator:
    MAX_STEPS = 20
    ALLOWED_WORKERS = {w.value for w in AllowedWorkerType}

    @staticmethod
    def _validate_step_order(raw_steps: Any) -> Optional[PlannerValidationIssue]:
        if not isinstance(raw_steps, list):
            return PlannerValidationIssue(
                code=PlannerValidationCode.MISSING_REQUIRED_FIELDS,
                message="'steps' must be a list",
            )

        if not raw_steps:
            return PlannerValidationIssue(
                code=PlannerValidationCode.EMPTY_PLAN,
                message="Planner response has no steps",
            )

        explicit_orders: List[int] = []
        for idx, step in enumerate(raw_steps):
            if not isinstance(step, dict):
                continue
            order_value = step.get("order")
            if order_value is None:
                order_value = step.get("step")
            if order_value is None:
                continue

            try:
                explicit_orders.append(int(order_value))
            except Exception:
                return PlannerValidationIssue(
                    code=PlannerValidationCode.INVALID_STEP_ORDER,
                    message=f"Step {idx + 1} has non-integer order value",
                    step_index=idx,
                )

        if not explicit_orders:
            return None

        expected = list(range(1, len(explicit_orders) + 1))
        if explicit_orders != expected:
            return PlannerValidationIssue(
                code=PlannerValidationCode.INVALID_STEP_ORDER,
                message=f"Step order must be strictly increasing from 1, got {explicit_orders}",
            )
        return None

    @staticmethod
    def validate_response_with_issues(
        raw_response: Dict[str, Any],
        enforce_tool_permissions: bool = False,
    ) -> PlannerValidationResult:
        issues: List[PlannerValidationIssue] = []
        if not isinstance(raw_response, dict):
            issues.append(
                PlannerValidationIssue(
                    code=PlannerValidationCode.MISSING_REQUIRED_FIELDS,
                    message="Planner response must be a JSON object",
                )
            )
            return PlannerValidationResult(plan=None, issues=issues)

        if "steps" not in raw_response:
            issues.append(
                PlannerValidationIssue(
                    code=PlannerValidationCode.MISSING_REQUIRED_FIELDS,
                    message="Planner response missing required field: steps",
                )
            )
            return PlannerValidationResult(plan=None, issues=issues)

        order_issue = PlannerSchemaValidator._validate_step_order(raw_response.get("steps"))
        if order_issue:
            issues.append(order_issue)
            if order_issue.code in {
                PlannerValidationCode.MISSING_REQUIRED_FIELDS,
                PlannerValidationCode.EMPTY_PLAN,
                PlannerValidationCode.INVALID_STEP_ORDER,
            }:
                return PlannerValidationResult(plan=None, issues=issues)

        try:
            validated = TaskPlan.model_validate(raw_response)
        except Exception as e:
            issues.append(
                PlannerValidationIssue(
                    code=PlannerValidationCode.MISSING_REQUIRED_FIELDS,
                    message=str(e),
                )
            )
            return PlannerValidationResult(plan=None, issues=issues)

        if not validated.steps:
            issues.append(
                PlannerValidationIssue(
                    code=PlannerValidationCode.EMPTY_PLAN,
                    message="Planner response has no steps after validation",
                )
            )
            return PlannerValidationResult(plan=None, issues=issues)

        if enforce_tool_permissions:
            from core.tasks.workers.capabilities import get_allowed_tools

            for idx, step in enumerate(validated.steps):
                worker_tools = get_allowed_tools(WorkerType(step.worker.value))
                if step.tool and not PlannerSchemaValidator.validate_tool_permission(step, worker_tools):
                    issues.append(
                        PlannerValidationIssue(
                            code=PlannerValidationCode.FORBIDDEN_TOOL,
                            message=f"Tool '{step.tool}' is not allowed for worker '{step.worker.value}'",
                            step_index=idx,
                        )
                    )

        if any(issue.code == PlannerValidationCode.FORBIDDEN_TOOL for issue in issues):
            return PlannerValidationResult(plan=None, issues=issues)

        return PlannerValidationResult(plan=validated, issues=issues)

    @staticmethod
    def validate_response(raw_response: Dict[str, Any]) -> Optional[TaskPlan]:
        result = PlannerSchemaValidator.validate_response_with_issues(raw_response)
        if result.plan is None:
            for issue in result.issues:
                logger.warning(f"Planner response validation failed [{issue.code}]: {issue.message}")
        return result.plan

    @staticmethod
    def _clean_json_payload(raw_response: str) -> str:
        cleaned = (raw_response or "").replace("```json", "").replace("```", "").strip()
        cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            cleaned = cleaned[first:last + 1]
        return cleaned

    @staticmethod
    def repair_and_validate_with_issues(
        raw_response: str,
        attempt_count: int = 1,
        enforce_tool_permissions: bool = False,
    ) -> PlannerValidationResult:
        cleaned = PlannerSchemaValidator._clean_json_payload(raw_response)
        issues: List[PlannerValidationIssue] = []

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            issues.append(
                PlannerValidationIssue(
                    code=PlannerValidationCode.MALFORMED_JSON,
                    message=f"Failed to parse planner JSON: {e}",
                )
            )
            return PlannerValidationResult(
                plan=None,
                issues=issues,
                repaired=True,
                attempt_count=attempt_count,
            )

        if not isinstance(parsed, dict):
            issues.append(
                PlannerValidationIssue(
                    code=PlannerValidationCode.MISSING_REQUIRED_FIELDS,
                    message="Planner payload must decode to a JSON object",
                )
            )
            return PlannerValidationResult(
                plan=None,
                issues=issues,
                repaired=True,
                attempt_count=attempt_count,
            )

        if "steps" not in parsed:
            parsed["steps"] = [
                {
                    "description": parsed.get("description", "Unknown step"),
                    "worker": "general",
                    "order": 1,
                }
            ]

        if not isinstance(parsed["steps"], list):
            parsed["steps"] = [{"description": str(parsed["steps"]), "worker": "general", "order": 1}]

        fixed_steps = []
        for i, step in enumerate(parsed["steps"]):
            if isinstance(step, str):
                fixed_steps.append({"description": step, "worker": "general", "order": i + 1})
            elif isinstance(step, dict):
                desc = step.get("description") or f"Step {i + 1}"
                worker = step.get("worker", "general")
                if isinstance(worker, str):
                    worker = worker.strip().lower()
                    if worker not in PlannerSchemaValidator.ALLOWED_WORKERS:
                        worker = "general"

                fixed_steps.append(
                    {
                        "description": str(desc)[:500],
                        "worker": worker,
                        "tool": step.get("tool"),
                        "parameters": (
                            step.get("parameters") if isinstance(step.get("parameters"), dict) else {}
                        ),
                        "order": step.get("order", i + 1),
                    }
                )

        parsed["steps"] = fixed_steps[: PlannerSchemaValidator.MAX_STEPS]
        validated = PlannerSchemaValidator.validate_response_with_issues(
            parsed,
            enforce_tool_permissions=enforce_tool_permissions,
        )
        validated.repaired = True
        validated.attempt_count = attempt_count
        return validated

    @staticmethod
    def repair_and_validate(
        raw_response: str,
        repair_attempt: bool = False
    ) -> Optional[TaskPlan]:
        result = PlannerSchemaValidator.repair_and_validate_with_issues(
            raw_response,
            attempt_count=2 if repair_attempt else 1,
            enforce_tool_permissions=False,
        )
        if result.plan is None:
            for issue in result.issues:
                logger.warning(f"Planner repair failed [{issue.code}]: {issue.message}")
        return result.plan

    @staticmethod
    def issues_to_error_payload(
        issues: List[PlannerValidationIssue],
        attempt_count: int,
    ) -> Dict[str, Any]:
        return {
            "code": "PLANNER_VALIDATION_FAILED",
            "attempt_count": attempt_count,
            "issues": [
                {
                    "code": issue.code.value,
                    "message": issue.message,
                    "step_index": issue.step_index,
                }
                for issue in issues
            ],
        }

    @staticmethod
    def enforce_guardrails(plan: TaskPlan) -> TaskPlan:
        enforced_steps = []
        for step in plan.steps:
            if step.worker.value not in PlannerSchemaValidator.ALLOWED_WORKERS:
                step = TaskPlanStep(
                    description=step.description,
                    worker=AllowedWorkerType.GENERAL,
                    tool=step.tool,
                    parameters=step.parameters,
                )
            enforced_steps.append(step)

        return TaskPlan(
            title=plan.title,
            description=plan.description,
            steps=enforced_steps[: PlannerSchemaValidator.MAX_STEPS],
        )

    @staticmethod
    def validate_tool_permission(
        step: TaskPlanStep,
        worker_tools: List[str]
    ) -> bool:
        if step.tool is None:
            return True

        tool_lower = step.tool.lower().strip()
        worker_tools_lower = [t.lower().strip() for t in worker_tools]

        return tool_lower in worker_tools_lower

    @staticmethod
    def repair_forbidden_tool(
        step: TaskPlanStep,
        worker_tools: List[str]
    ) -> TaskPlanStep:
        if step.tool is None:
            return step

        if not PlannerSchemaValidator.validate_tool_permission(step, worker_tools):
            logger.warning(
                f"Tool '{step.tool}' not allowed for worker '{step.worker.value}'. Removing tool."
            )
            return TaskPlanStep(
                description=step.description,
                worker=step.worker,
                tool=None,
                parameters={},
                order=step.order,
            )

        return step
