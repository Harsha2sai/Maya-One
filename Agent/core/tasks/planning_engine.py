import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from config.settings import settings
from core.context.role_context_builders.planner_context_builder import PlannerContextBuilder
from core.llm.llm_roles import LLMRole
from core.llm.role_llm import RoleLLM
from core.observability.trace_context import current_trace_id, set_trace_context
from core.tasks.planner_schema_validator import (
    PlannerSchemaValidator,
    PlannerValidationCode,
    PlannerValidationIssue,
    TaskPlan,
)
from core.tasks.task_steps import TaskStep, TaskStepStatus
from providers.factory import ProviderFactory

logger = logging.getLogger(__name__)


@dataclass
class PlanGenerationResult:
    steps: List[TaskStep]
    plan_failed: bool = False
    error_payload: Optional[Dict[str, Any]] = None
    raw_response: str = ""


class _CompatSmartLLM:
    """
    Adapter for older code paths where we only have a raw provider LLM.
    RoleLLM expects a SmartLLM-like .chat(chat_ctx=..., tools=...) surface.
    """

    def __init__(self, base_llm: Any):
        self._base_llm = base_llm

    def chat(self, *, chat_ctx: Any, tools: Optional[List[Any]] = None, **kwargs):
        return self._base_llm.chat(chat_ctx=chat_ctx, tools=tools)


class PlanningEngine:
    TASK_MANAGEMENT_TOOLS = {
        "create_task",
        "list_tasks",
        "get_task_status",
        "ask_task_status",
        "cancel_task",
    }
    MAX_REPAIR_ATTEMPTS = 2

    def __init__(self, smart_llm: Any = None):
        resolved_smart_llm = smart_llm
        if resolved_smart_llm is None:
            try:
                base_llm = ProviderFactory.get_llm(settings.llm_provider, settings.llm_model)
                resolved_smart_llm = _CompatSmartLLM(base_llm)
                logger.info("🧩 PlanningEngine initialized using ProviderFactory fallback LLM.")
            except Exception as e:
                logger.error(f"❌ PlanningEngine failed to initialize fallback LLM: {e}")
                resolved_smart_llm = None

        self.role_llm = RoleLLM(resolved_smart_llm) if resolved_smart_llm else None

    @staticmethod
    def _normalize_worker(raw_worker: Any) -> str:
        worker = str(raw_worker or "general").strip().lower()
        if worker in {"general", "research", "automation", "system"}:
            return worker
        return "general"

    @classmethod
    def _assign_worker_for_step(cls, tool_name: Any, raw_worker: Any = None) -> str:
        worker = cls._normalize_worker(raw_worker)
        normalized_tool = str(tool_name or "").strip().lower()
        if not normalized_tool:
            return worker

        if normalized_tool in {
            "web_search",
            "search_web",
            "google_search",
            "browser_open",
            "summarize_url",
            "read_url",
        }:
            return "research"
        if normalized_tool in {
            "run_shell_command",
            "system_control",
            "file_write",
            "file_delete",
            "app_control",
            "open_app",
        }:
            return "system"
        if normalized_tool in {
            "send_email",
            "create_calendar_event",
            "spotify_play",
            "reminder_create",
        }:
            return "automation"
        return worker

    @staticmethod
    def _extract_user_request(user_request: str) -> str:
        """
        Extract the user intent text from augmented planner context strings.
        """
        raw = (user_request or "").strip()
        if not raw:
            return "user request"

        marker = re.search(r"user request\s*:\s*(.+)$", raw, flags=re.IGNORECASE | re.DOTALL)
        if marker:
            raw = marker.group(1).strip()

        # Normalize any memory/chat transcript artifacts that can leak into fallback descriptions.
        raw = re.sub(r"^\s*relevant past memories:\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"(?im)^\s*-\s*(user|assistant)\s*:\s*", "", raw)
        raw = " ".join(raw.split())
        return raw or "user request"

    @classmethod
    def _clean_step_description(cls, description: str, user_request: str) -> str:
        """
        Keep step descriptions user-facing and deterministic across runtime paths.
        """
        text = (description or "").strip()
        if not text:
            return cls._extract_user_request(user_request)

        text = re.sub(r"^\s*understand and execute:\s*", "", text, flags=re.IGNORECASE)
        if "relevant past memories" in text.lower():
            text = cls._extract_user_request(user_request)
        text = re.sub(r"(?im)^\s*-\s*(user|assistant)\s*:\s*", "", text)
        text = " ".join(text.split())
        return (text or cls._extract_user_request(user_request))[:500]

    @staticmethod
    def _fallback_step(user_request: str) -> List[TaskStep]:
        text = PlanningEngine._extract_user_request(user_request)
        return [
            TaskStep(
                description=text[:240],
                worker="general",
                status=TaskStepStatus.PENDING,
            )
        ]

    @staticmethod
    def _fallback_step_with_error(user_request: str, error_payload: Dict[str, Any]) -> List[TaskStep]:
        fallback = PlanningEngine._fallback_step(user_request)
        if fallback:
            fallback[0].metadata = fallback[0].metadata or {}
            fallback[0].metadata["planner_error"] = error_payload
        return fallback

    @classmethod
    def _build_deterministic_plan(cls, user_request: str) -> Optional[PlanGenerationResult]:
        request_text = cls._extract_user_request(user_request)
        reminder_then_open = re.search(
            r"set (?:a )?reminder to (?P<reminder>.+?) in (?P<delay>\d+)\s*(?P<unit>minutes?|hours?)\s+and (?:then )?open (?P<app>.+?)[\.\!\?]?$",
            request_text,
            flags=re.IGNORECASE,
        )
        if not reminder_then_open:
            return None

        reminder_text = reminder_then_open.group("reminder").strip()
        delay_value = int(reminder_then_open.group("delay"))
        delay_unit = reminder_then_open.group("unit").strip().lower()
        app_name = reminder_then_open.group("app").strip().rstrip(".!?")
        offset_phrase = f"in {delay_value} {delay_unit}"

        plan_payload = {
            "title": f"Reminder and app launch for {app_name}",
            "steps": [
                {
                    "seq": 1,
                    "title": "Set reminder",
                    "description": f"Set a reminder to {reminder_text} {offset_phrase}.",
                    "tool": "set_reminder",
                    "worker": "general",
                    "parameters": {
                        "text": reminder_text,
                        "time": offset_phrase,
                    },
                },
                {
                    "seq": 2,
                    "title": "Open app",
                    "description": f"Open {app_name}.",
                    "tool": "open_app",
                    "worker": "system",
                    "parameters": {
                        "app_name": app_name,
                    },
                },
            ],
        }
        steps = [
            TaskStep(
                description=plan_payload["steps"][0]["description"],
                tool="set_reminder",
                parameters=dict(plan_payload["steps"][0]["parameters"]),
                worker="general",
                status=TaskStepStatus.PENDING,
            ),
            TaskStep(
                description=plan_payload["steps"][1]["description"],
                tool="open_app",
                parameters=dict(plan_payload["steps"][1]["parameters"]),
                worker="system",
                status=TaskStepStatus.PENDING,
            ),
        ]
        logger.info(
            "planner_deterministic_plan_applied plan_ms=0 pattern=reminder_then_open step_count=%s",
            len(steps),
        )
        return PlanGenerationResult(
            steps=steps,
            plan_failed=False,
            error_payload=None,
            raw_response=json.dumps(plan_payload, ensure_ascii=True),
        )

    @classmethod
    def _sanitize_planner_tool_step(
        cls,
        tool_name: str,
        parsed_args: Dict[str, Any],
        default_worker: str = "general",
        fallback_description: Optional[str] = None,
    ) -> TaskStep:
        """
        Prevent planner outputs from recursively managing the task system.
        Planner should decompose tasks, not call task-management tools.
        """
        normalized_tool = (tool_name or "").strip().lower()
        if normalized_tool in cls.TASK_MANAGEMENT_TOOLS:
            arg_desc = str((parsed_args or {}).get("description") or "").strip()
            safe_desc = cls._clean_step_description(
                arg_desc or fallback_description or "Execute the requested work item",
                user_request=arg_desc or fallback_description or "",
            )
            logger.warning(
                "⚠️ Planner emitted task-management tool '%s'. "
                "Converting to reasoning step to avoid recursive task creation.",
                normalized_tool,
            )
            return TaskStep(
                description=safe_desc[:500],
                worker=cls._normalize_worker(default_worker),
                tool=None,
                parameters={},
                status=TaskStepStatus.PENDING,
            )

        return TaskStep(
            description=(fallback_description or f"Execute {tool_name}").strip()[:500],
            worker=cls._normalize_worker(default_worker),
            tool=tool_name,
            parameters=parsed_args if isinstance(parsed_args, dict) else {},
            status=TaskStepStatus.PENDING,
        )

    @staticmethod
    def _extract_json_payload(response_text: str) -> str:
        clean_text = (response_text or "").replace("```json", "").replace("```", "").strip()
        if not clean_text:
            return ""

        # Prefer largest object-like slice when extra prose surrounds JSON.
        first = clean_text.find("{")
        last = clean_text.rfind("}")
        if first != -1 and last != -1 and last > first:
            return clean_text[first:last + 1]
        return clean_text

    @staticmethod
    def _schema_text() -> str:
        schema_obj = TaskPlan.model_json_schema()
        return json.dumps(schema_obj, ensure_ascii=True, separators=(",", ":"))

    @staticmethod
    def _extract_tool_calls(chunk: Any) -> Tuple[str, List[Any]]:
        delta_content = ""
        tool_calls: List[Any] = []

        # Robust chunk handling across providers.
        if hasattr(chunk, "choices") and chunk.choices:
            delta = getattr(chunk.choices[0], "delta", None)
            delta_content = getattr(delta, "content", "") or ""
            tool_calls = getattr(delta, "tool_calls", []) or []
        elif hasattr(chunk, "delta") and chunk.delta:
            delta = chunk.delta
            delta_content = getattr(delta, "content", "") or ""
            tool_calls = getattr(delta, "tool_calls", []) or []
        elif hasattr(chunk, "content"):
            delta_content = chunk.content or ""

        return delta_content, tool_calls

    async def _run_planner_prompt(self, prompt_text: str) -> Tuple[str, List[TaskStep]]:
        if not self.role_llm:
            return "", []

        response_text = ""
        chat_ctx = PlannerContextBuilder.build(user_request=prompt_text)
        stream = await self.role_llm.chat(
            role=LLMRole.PLANNER,
            chat_ctx=chat_ctx,
            tools=[],  # PLANNER never receives tools.
        )

        tool_calls_buffer: Dict[Any, Dict[str, str]] = {}
        try:
            async for chunk in stream:
                delta_content, tool_calls = self._extract_tool_calls(chunk)
                if delta_content:
                    response_text += delta_content

                for tc in tool_calls:
                    call_index = getattr(tc, "index", None)
                    if call_index is None:
                        call_index = getattr(tc, "id", f"tc_{len(tool_calls_buffer)}")

                    entry = tool_calls_buffer.setdefault(call_index, {"name": "", "arguments": ""})
                    if hasattr(tc, "function") and tc.function:
                        entry["name"] += getattr(tc.function, "name", "") or ""
                        entry["arguments"] += getattr(tc.function, "arguments", "") or ""
                    else:
                        entry["name"] += getattr(tc, "name", "") or ""
                        entry["arguments"] += getattr(tc, "arguments", "") or ""
        finally:
            close_fn = getattr(stream, "aclose", None)
            if callable(close_fn):
                try:
                    await close_fn()
                except Exception as e:
                    logger.debug(f"⚠️ Failed to close PLANNER stream: {e}")

        collected_tool_steps: List[TaskStep] = []
        for tc in tool_calls_buffer.values():
            name = (tc.get("name") or "").strip()
            if not name:
                continue

            raw_args = (tc.get("arguments") or "").strip()
            parsed_args: Dict[str, Any] = {}
            if raw_args and raw_args not in {"null", "None"}:
                try:
                    parsed_args = json.loads(raw_args)
                    if not isinstance(parsed_args, dict):
                        parsed_args = {}
                except Exception:
                    parsed_args = {}

            collected_tool_steps.append(
                self._sanitize_planner_tool_step(
                    tool_name=name,
                    parsed_args=parsed_args,
                    default_worker="general",
                    fallback_description=f"Execute {name}",
                )
            )

        return response_text, collected_tool_steps

    @staticmethod
    def _validate_task_plan_payload(payload: str) -> Tuple[Optional[TaskPlan], List[PlannerValidationIssue]]:
        if not payload.strip():
            return None, [
                PlannerValidationIssue(
                    code=PlannerValidationCode.MALFORMED_JSON,
                    message="Planner payload is empty",
                )
            ]

        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as e:
            return None, [
                PlannerValidationIssue(
                    code=PlannerValidationCode.MALFORMED_JSON,
                    message=f"Direct parse failed: {e}",
                )
            ]

        result = PlannerSchemaValidator.validate_response_with_issues(
            raw,
            enforce_tool_permissions=True,
        )
        if result.plan is not None:
            return result.plan, result.issues

        if result.issues and all(
            issue.code == PlannerValidationCode.FORBIDDEN_TOOL for issue in result.issues
        ):
            relaxed_result = PlannerSchemaValidator.validate_response_with_issues(
                raw,
                enforce_tool_permissions=False,
            )
            if relaxed_result.plan is not None:
                return relaxed_result.plan, result.issues

        return result.plan, result.issues

    def _build_repair_prompt(
        self,
        *,
        invalid_payload: str,
        issues: List[PlannerValidationIssue],
        attempt_number: int,
    ) -> str:
        issues_text = "\n".join(
            f"- {issue.code.value}: {issue.message}" for issue in issues
        ) or "- UNKNOWN: Validation failed"

        return (
            "Repair the planner JSON to match the TaskPlan schema exactly.\n"
            "Return ONLY valid JSON (no markdown, no prose).\n"
            f"Repair attempt: {attempt_number}/{self.MAX_REPAIR_ATTEMPTS}.\n\n"
            "Schema:\n"
            f"{self._schema_text()}\n\n"
            "Validation issues:\n"
            f"{issues_text}\n\n"
            "Invalid planner output:\n"
            f"{invalid_payload}"
        )

    def _steps_from_plan(self, validated_plan: TaskPlan, context_str: str) -> List[TaskStep]:
        from core.tasks.task_steps import WorkerType
        from core.tasks.workers.capabilities import get_allowed_tools

        steps: List[TaskStep] = []
        for planned_step in validated_plan.steps:
            worker_type = WorkerType(planned_step.worker.value)
            allowed_tools = get_allowed_tools(worker_type)
            planned_step = PlannerSchemaValidator.repair_forbidden_tool(planned_step, allowed_tools)

            normalized_tool = (planned_step.tool or "").strip().lower() if planned_step.tool else ""
            step_desc = self._clean_step_description(planned_step.description, context_str)
            if normalized_tool in self.TASK_MANAGEMENT_TOOLS:
                arg_desc = ""
                if isinstance(planned_step.parameters, dict):
                    arg_desc = str(planned_step.parameters.get("description") or "").strip()
                steps.append(
                    TaskStep(
                        description=self._clean_step_description(
                            arg_desc or step_desc or "Execute planned task step",
                            context_str,
                        ),
                        worker=self._assign_worker_for_step(None, planned_step.worker.value),
                        tool=None,
                        parameters={},
                        status=TaskStepStatus.PENDING,
                    )
                )
                continue

            steps.append(
                TaskStep(
                    description=step_desc,
                    worker=self._assign_worker_for_step(planned_step.tool, planned_step.worker.value),
                    tool=planned_step.tool,
                    parameters=planned_step.parameters,
                    status=TaskStepStatus.PENDING,
                )
            )
        return steps

    async def generate_plan_result(self, context_str: str) -> PlanGenerationResult:
        """
        Decomposes a user request into actionable steps using the LLM (PLANNER Role).
        All LLM planner outputs are validated against TaskPlan before conversion.
        """
        response_text = ""
        try:
            set_trace_context(trace_id=current_trace_id())
            deterministic_plan = self._build_deterministic_plan(context_str)
            if deterministic_plan is not None:
                return deterministic_plan
            if not self.role_llm:
                logger.error("❌ Planning failed: RoleLLM unavailable.")
                return PlanGenerationResult(steps=self._fallback_step(context_str))

            logger.info("🧠 PLANNER ROLE STARTED")
            response_text, collected_tool_steps = await self._run_planner_prompt(context_str)

            if not response_text.strip():
                if collected_tool_steps:
                    logger.warning(
                        "⚠️ Planner yielded %s tool calls instead of JSON. Using sanitized tool steps.",
                        len(collected_tool_steps),
                    )
                    return PlanGenerationResult(steps=collected_tool_steps)

                logger.error("❌ Planning failed: Empty response from LLM")
                return PlanGenerationResult(steps=self._fallback_step(context_str))

            payload = self._extract_json_payload(response_text)
            if not payload:
                logger.error("❌ Planning failed: cleaned planner response is empty")
                return PlanGenerationResult(
                    steps=collected_tool_steps or self._fallback_step(context_str),
                    raw_response=response_text,
                )

            attempted_payload = payload
            all_issues: List[PlannerValidationIssue] = []

            for attempt in range(self.MAX_REPAIR_ATTEMPTS + 1):
                validated_plan, issues = self._validate_task_plan_payload(attempted_payload)
                all_issues.extend(issues)
                if validated_plan is not None:
                    validated_plan = PlannerSchemaValidator.enforce_guardrails(validated_plan)
                    steps = self._steps_from_plan(validated_plan, context_str)
                    logger.info("✅ Validated TaskPlan with %s steps.", len(steps))
                    if steps:
                        return PlanGenerationResult(steps=steps, raw_response=response_text)
                    break

                if attempt >= self.MAX_REPAIR_ATTEMPTS:
                    break

                repair_prompt = self._build_repair_prompt(
                    invalid_payload=attempted_payload,
                    issues=issues,
                    attempt_number=attempt + 1,
                )
                logger.warning(
                    "planner_validation_failed attempt=%s/%s issues=%s",
                    attempt + 1,
                    self.MAX_REPAIR_ATTEMPTS,
                    [issue.code.value for issue in issues],
                )
                repaired_response, _ = await self._run_planner_prompt(repair_prompt)
                attempted_payload = self._extract_json_payload(repaired_response) or repaired_response

            error_payload = PlannerSchemaValidator.issues_to_error_payload(
                all_issues,
                attempt_count=self.MAX_REPAIR_ATTEMPTS,
            )
            logger.error(
                "planner_plan_failed code=%s attempts=%s issues=%s",
                error_payload.get("code"),
                error_payload.get("attempt_count"),
                error_payload.get("issues"),
            )
            failed_steps = collected_tool_steps or self._fallback_step_with_error(context_str, error_payload)
            return PlanGenerationResult(
                steps=failed_steps,
                plan_failed=True,
                error_payload=error_payload,
                raw_response=response_text,
            )

        except Exception as e:
            logger.error(f"❌ Planning failed: {e}")
            return PlanGenerationResult(steps=self._fallback_step(context_str), raw_response=response_text)

    async def generate_plan(self, context_str: str) -> List[TaskStep]:
        """
        Backward-compatible wrapper for existing call sites/tests.
        """
        result = await self.generate_plan_result(context_str)
        return result.steps
