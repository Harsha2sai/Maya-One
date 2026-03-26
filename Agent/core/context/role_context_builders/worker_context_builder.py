import logging
from typing import Any, List
from livekit.agents.llm import ChatContext, ChatMessage
from core.prompts import get_worker_base_prompt, get_worker_overlay

logger = logging.getLogger(__name__)


class WorkerContextBuilder:
    """Builds context for Worker execution, including step details."""

    @staticmethod
    def _normalize_worker_type(worker_type: Any) -> str:
        normalized = str(worker_type or "general").strip().lower()
        if normalized in {"general", "research", "system", "automation"}:
            return normalized
        return "general"

    @staticmethod
    def build(
        task_description: Any,
        step_description: Any,
        previous_result: str = None,
        worker_type: Any = None,
        host_capability_profile: Any = None,
    ) -> ChatContext:
        messages = []

        task_obj = task_description
        step_obj = step_description
        task_text = getattr(task_obj, "description", None) or getattr(task_obj, "title", None) or str(task_description)
        step_text = getattr(step_obj, "description", None) or str(step_description)
        normalized_worker_type = WorkerContextBuilder._normalize_worker_type(
            worker_type if worker_type is not None else getattr(step_obj, "worker", None)
        )

        # 1. System Prompt
        prompt_parts: list[str] = [
            get_worker_base_prompt(),
            get_worker_overlay(normalized_worker_type),
        ]
        if host_capability_profile is None and normalized_worker_type in {"system", "automation"}:
            try:
                from core.runtime.global_agent import GlobalAgentContainer

                host_capability_profile = GlobalAgentContainer.get_host_capability_profile(refresh=True)
            except Exception as exc:
                logger.debug("worker_host_profile_unavailable worker_type=%s error=%s", normalized_worker_type, exc)

        if host_capability_profile is not None and normalized_worker_type in {"system", "automation"}:
            prompt_parts.append(host_capability_profile.to_prompt_block())
            logger.info("host_capability_injected worker_type=%s", normalized_worker_type)

        sys_content = "\n\n".join(part for part in prompt_parts if part)
        logger.info(
            "worker_context_built worker_type=%s prompt_source=worker_%s",
            normalized_worker_type,
            normalized_worker_type,
        )
        messages.append(ChatMessage(role="system", content=[sys_content]))

        # 2. Step Context
        content_str = f"Task: {task_text}\nStep: {step_text}\n"
        if previous_result:
            content_str += f"Previous Step Result: {previous_result}\n"

        messages.append(ChatMessage(role="user", content=[content_str]))

        return ChatContext(messages)
