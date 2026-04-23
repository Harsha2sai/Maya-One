"""Action-state constants and route precedence policy."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RoutePrecedence(IntEnum):
    FAST_PATH_EXPLICIT = 1
    SYSTEM_PLANNER_EXPLICIT = 2
    LLM_TOOL_DETERMINISTIC = 3
    PLANNER_MULTI_STEP = 4
    CONVERSATIONAL_FALLBACK = 5


@dataclass(frozen=True)
class ActionStateConfig:
    max_opened_apps: int = 5
    max_search_queries: int = 3
    max_actions: int = 10
    default_ttl_seconds: int = 300
    search_query_ttl_seconds: int = 600
    last_action_ttl_seconds: int = 1800
    last_action_max_turns: int = 5
    active_entity_ttl_seconds: int = 1800
    active_entity_max_turns: int = 8
    active_entity_max_non_research_turns: int = 3
    pending_scheduling_ttl_seconds: int = 600
    pending_scheduling_max_turns: int = 2


@dataclass(frozen=True)
class VerificationPolicy:
    max_retries: int = 1
    retry_delay_ms: int = 500
    strong_only_success_claim: bool = True
