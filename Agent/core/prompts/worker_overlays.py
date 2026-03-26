"""Worker prompt overlays for Phase 9C."""

from __future__ import annotations

from .worker_automation_prompt import get_worker_automation_prompt
from .worker_base_prompt import get_worker_base_prompt
from .worker_general_prompt import get_worker_general_prompt
from .worker_research_prompt import get_worker_research_prompt
from .worker_system_prompt import get_worker_system_prompt

_WORKER_PROMPT_MAP = {
    "general": get_worker_general_prompt,
    "research": get_worker_research_prompt,
    "system": get_worker_system_prompt,
    "automation": get_worker_automation_prompt,
}


def get_worker_overlay(worker_type: str | None) -> str:
    normalized = str(worker_type or "general").strip().lower() or "general"
    prompt_factory = _WORKER_PROMPT_MAP.get(normalized, get_worker_general_prompt)
    return prompt_factory()


def get_worker_prompt(worker_type: str | None = None) -> str:
    base_prompt = get_worker_base_prompt()
    overlay = get_worker_overlay(worker_type)
    return f"{base_prompt}\n\n{overlay}" if overlay else base_prompt
