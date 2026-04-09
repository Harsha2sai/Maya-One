"""Task execution and report export helpers."""
from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from typing import Any

from config.settings import settings
from core.governance.types import UserRole
from core.observability.trace_context import (
    current_trace_id,
    get_trace_context,
    set_trace_context,
)
from core.tasks.task_models import Task, TaskStatus
from core.telemetry.runtime_metrics import RuntimeMetrics

logger = logging.getLogger(__name__)


class TaskRuntimeService:
    """Owns task planning, report export, and worker lifecycle flows."""

    def __init__(self, *, owner: Any, coerce_user_role_fn: Any):
        self._owner = owner
        self._coerce_user_role = coerce_user_role_fn

    async def handle_task_request(
        self,
        user_text: str,
        user_id: str,
        tool_context: Any = None,
    ) -> str:
        report_export_result = await self._owner._try_handle_report_export_task(
            user_text=user_text,
            user_id=user_id,
            tool_context=tool_context,
        )
        if report_export_result is not None:
            return report_export_result

        planning_task_id = getattr(tool_context, "task_id", None) or f"handoff-plan:{uuid.uuid4()}"
        host_profile = self._owner._get_host_capability_profile(refresh=True)
        handoff_target = self._owner._consume_handoff_signal(
            target_agent="planner",
            execution_mode="planning",
            reason="task_request_detected",
            context_hint=str(user_text or "")[:160],
        )
        handoff_request = self._owner._build_handoff_request(
            target_agent=handoff_target,
            message=user_text,
            user_id=user_id,
            execution_mode="planning",
            tool_context=tool_context,
            handoff_reason="task_request_detected",
            force_task_id=planning_task_id,
            host_profile=host_profile,
        )
        handoff_result = await self._owner._handoff_manager.delegate(handoff_request)
        if handoff_result.status == "failed":
            return "I couldn't start planning that request safely."

        session_id = getattr(getattr(self._owner, "room", None), "name", None) or "console_session"
        set_trace_context(
            trace_id=current_trace_id(),
            session_id=session_id,
            user_id=user_id,
        )

        memory_session_id = getattr(getattr(self._owner, "room", None), "name", None) or session_id
        memory_context = await self._owner._retrieve_memory_context_async(
            user_text,
            origin="chat",
            routing_mode_type="informational",
            user_id=user_id,
            session_id=memory_session_id,
        )
        augmented_sections: list[str] = []
        if host_profile:
            augmented_sections.append(self._owner._host_profile_to_text(host_profile))
        if memory_context:
            augmented_sections.append(memory_context)
            augmented_sections.append(f"User Request: {user_text}")
        else:
            augmented_sections.append(user_text)
        augmented_text = "\n".join(section for section in augmented_sections if section)

        logger.info("🤔 Planning task for: %s", user_text)
        if not str(user_id).startswith("livekit:"):
            await self._owner._announce(f"I'm planning how to handle: {user_text}")

        plan_result = None
        plan_result_call = getattr(self._owner.planning_engine, "generate_plan_result", None)
        if (
            inspect.ismethod(plan_result_call)
            or inspect.isfunction(plan_result_call)
            or inspect.iscoroutinefunction(plan_result_call)
        ):
            maybe_plan_result = plan_result_call(augmented_text)
            if hasattr(maybe_plan_result, "__await__"):
                plan_result = await maybe_plan_result

        if plan_result is None:
            steps_legacy = await self._owner.planning_engine.generate_plan(augmented_text)
            plan_result = type(
                "PlanResult",
                (),
                {
                    "steps": steps_legacy,
                    "plan_failed": False,
                    "error_payload": None,
                },
            )()

        steps = plan_result.steps
        if not steps and not plan_result.plan_failed:
            return "I couldn't create a plan for that request."

        task_status = TaskStatus.PLAN_FAILED if plan_result.plan_failed else TaskStatus.PENDING
        task = Task(
            user_id=user_id,
            title=f"Task: {user_text[:30]}...",
            description=user_text,
            steps=steps,
            status=task_status,
        )
        precreate_trace = get_trace_context()
        default_role = self._coerce_user_role(
            getattr(settings, "default_client_role", "USER"),
            default_role=UserRole.USER,
        )
        task.metadata = task.metadata or {}
        task.metadata["trace_id"] = precreate_trace.get("trace_id")
        task.metadata["session_id"] = precreate_trace.get("session_id")
        task.metadata["user_role"] = default_role.name

        turn_id = None
        if tool_context is not None:
            turn_id = getattr(tool_context, "turn_id", None)
        if not turn_id:
            turn_id = (self._owner.turn_state or {}).get("current_turn_id")
        if turn_id:
            task.metadata["turn_id"] = turn_id
        if tool_context is not None:
            ctx_trace_id = getattr(tool_context, "trace_id", None)
            if ctx_trace_id:
                task.metadata["trace_id"] = ctx_trace_id
            ctx_session_id = getattr(tool_context, "session_id", None)
            if ctx_session_id:
                task.metadata["session_id"] = ctx_session_id
            ctx_conversation_id = getattr(tool_context, "conversation_id", None)
            if ctx_conversation_id:
                task.metadata["conversation_id"] = ctx_conversation_id
            participant_metadata = getattr(tool_context, "participant_metadata", None)
            if isinstance(participant_metadata, dict):
                meta_conversation_id = str(participant_metadata.get("conversation_id") or "").strip()
                if meta_conversation_id:
                    task.metadata["conversation_id"] = meta_conversation_id

        if plan_result.plan_failed and plan_result.error_payload:
            task.metadata["planner_error"] = plan_result.error_payload
        planner_taskplan_json = getattr(plan_result, "raw_response", None)
        if planner_taskplan_json:
            task.metadata["planner_taskplan_json"] = planner_taskplan_json

        success = await self._owner._maybe_await(self._owner.task_store.create_task(task))
        if not success:
            return "Failed to save the task."

        trace_ctx = set_trace_context(task_id=task.id)
        if plan_result.plan_failed:
            self._owner.turn_state["pending_task_completion_summary"] = "I wasn't able to plan that task."
            structured_error = {
                "event": "planner_plan_failed",
                "task_id": task.id,
                "trace_id": trace_ctx.get("trace_id"),
                "attempts": (plan_result.error_payload or {}).get("attempt_count"),
                "issues": (plan_result.error_payload or {}).get("issues", []),
            }
            logger.error("❌ PLAN_FAILED %s", structured_error)
            await self._owner._maybe_await(
                self._owner.task_store.add_log(task.id, f"PLAN_FAILED: {structured_error}")
            )
            await self._owner._handle_task_worker_event(
                {
                    "event_type": "plan_failed",
                    "task_id": task.id,
                    "trace_id": trace_ctx.get("trace_id"),
                    "message": "I wasn't able to plan that task.",
                    "voice_text": "I wasn't able to plan that task.",
                }
            )
            return "I couldn't create a safe executable plan for that request."

        await self._owner._ensure_task_worker(user_id)
        RuntimeMetrics.increment("tasks_created_total")
        logger.info(
            "✅ Task %s created with %s steps (trace_id=%s).",
            task.id,
            len(steps),
            trace_ctx.get("trace_id"),
        )

        response = self._owner._summarize_task_start(user_text, steps)
        self._owner.turn_state["pending_task_completion_summary"] = response
        asyncio.create_task(
            self._owner.memory.store_conversation_turn(
                user_msg=user_text,
                assistant_msg=response,
                metadata={"source": "conversation", "role": "planner"},
                user_id=user_id,
                session_id=memory_session_id,
            )
        )
        return response

    async def try_handle_report_export_task(
        self,
        *,
        user_text: str,
        user_id: str,
        tool_context: Any = None,
    ) -> str | None:
        if not self._owner._is_report_export_request(user_text):
            return None

        user_role = self._coerce_user_role(
            getattr(tool_context, "user_role", None) if tool_context is not None else None,
            default_role=UserRole.USER,
        )
        if user_role < UserRole.TRUSTED:
            return (
                "I can prepare the report summary, but saving files to Downloads needs TRUSTED role. "
                "Enable TRUSTED role in client metadata and retry."
            )

        session_id = (
            getattr(tool_context, "session_id", None)
            or self._owner._current_session_id
            or getattr(getattr(self._owner, "room", None), "name", None)
            or "console_session"
        )
        trace_id = (
            getattr(tool_context, "trace_id", None)
            or current_trace_id()
            or str(uuid.uuid4())
        )
        research_query = self._owner._extract_report_focus_query(user_text) or user_text

        try:
            research_result = await self._owner._run_inline_research_pipeline(
                query=research_query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error("report_export_research_failed error=%s", exc, exc_info=True)
            return "I couldn't prepare the report content yet. Please try again."

        if not research_result or not str(getattr(research_result, "summary", "")).strip():
            return "I couldn't prepare a reliable report summary right now."

        output_path = self._owner._build_report_output_path(research_query)
        report_markdown = self.compose_report_markdown(
            query=research_query,
            summary=str(research_result.summary or "").strip(),
            sources=list(getattr(research_result, "sources", []) or []),
        )
        result, invocation = await self._owner._execute_tool_call(
            "create_docx",
            {"content": report_markdown, "path": output_path},
            user_id,
            tool_context=tool_context,
        )
        if invocation.status != "success":
            result_message = str((result or {}).get("message") or "").strip()
            if "permission denied" in result_message.lower() or "access denied" in result_message.lower():
                return (
                    "Report content is ready, but I don't have permission to save in Downloads. "
                    "Use TRUSTED role and retry."
                )
            return (
                "I prepared the report content, but saving the document failed. "
                "Please retry once."
            )

        return (
            f"I created a report and saved it to {output_path}. "
            f"Sources included: {len(getattr(research_result, 'sources', []) or [])}."
        )

    @staticmethod
    def compose_report_markdown(query: str, summary: str, sources: list[Any]) -> str:
        lines = [
            f"# Research Report: {query}",
            "",
            "## Executive Summary",
            summary or "No summary available.",
            "",
            "## Sources",
        ]
        if sources:
            for idx, source in enumerate(sources[:12], start=1):
                if hasattr(source, "title"):
                    title = str(getattr(source, "title", "") or f"Source {idx}")
                    url = str(getattr(source, "url", "") or "")
                    snippet = str(getattr(source, "snippet", "") or "").strip()
                else:
                    source_dict = source if isinstance(source, dict) else {}
                    title = str(source_dict.get("title") or f"Source {idx}")
                    url = str(source_dict.get("url") or "")
                    snippet = str(source_dict.get("snippet") or "").strip()
                line = f"- [{idx}] {title}"
                if url:
                    line += f" ({url})"
                if snippet:
                    line += f" - {snippet}"
                lines.append(line)
        else:
            lines.append("- No sources were available.")
        return "\n".join(lines).strip() + "\n"

    async def ensure_task_worker(self, user_id: str) -> None:
        async with self._owner._task_worker_lock:
            existing = self._owner._task_workers.get(user_id)
            if existing and getattr(existing, "is_running", False):
                if getattr(self._owner, "room", None) is not None:
                    existing.set_room(self._owner.room)
                return

            from core.tasks.task_worker import TaskWorker

            smart_llm = getattr(self._owner.agent, "smart_llm", None)
            worker = TaskWorker(
                user_id=user_id,
                memory_manager=self._owner.memory,
                smart_llm=smart_llm,
                room=getattr(self._owner, "room", None),
                event_notifier=self._owner._handle_task_worker_event,
            )
            if hasattr(worker, "set_message_bus"):
                worker.set_message_bus(getattr(self._owner, "_message_bus", None))
            await worker.start()
            self._owner._task_workers[user_id] = worker
            logger.info("👷 TaskWorker started for %s", user_id)

    async def shutdown(self) -> None:
        async with self._owner._task_worker_lock:
            workers = list(self._owner._task_workers.values())
            self._owner._task_workers.clear()

        for worker in workers:
            try:
                await worker.stop()
            except Exception as exc:
                logger.warning("⚠️ Failed to stop TaskWorker cleanly: %s", exc)
