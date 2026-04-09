"""Centralized handoff validation and specialist delegation manager."""

from __future__ import annotations

import logging
import asyncio
import time
from core.agents.contracts import AgentHandoffRequest, AgentHandoffResult, HandoffSignal
from core.agents.subagent_circuit_breaker import SubagentCircuitBreaker
from config.settings import settings
from core.telemetry.runtime_metrics import RuntimeMetrics

logger = logging.getLogger(__name__)


class HandoffValidationError(ValueError):
    """Raised when a handoff request violates Phase 9A invariants."""


class HandoffLimitError(RuntimeError):
    """Raised when runtime operational caps are exceeded."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class HandoffManager:
    MAX_DEPTH_STAGE_A = 2
    MAX_DEPTH_STAGE_B = 3
    ALLOWED_TARGETS = {
        "research",
        "system_operator",
        "planner",
        "media",
        "scheduling",
        "subagent_coder",
        "subagent_reviewer",
        "subagent_architect",
        "team_coding",
        "team_review",
        "project_manager",
    }
    SIGNAL_TO_TARGET = {
        "transfer_to_research": "research",
        "transfer_to_system_operator": "system_operator",
        "transfer_to_planner": "planner",
        "transfer_to_media": "media",
        "transfer_to_scheduling": "scheduling",
    }
    SUBAGENT_TARGETS = {
        "subagent_coder",
        "subagent_reviewer",
        "subagent_architect",
        "team_coding",
        "team_review",
        "project_manager",
    }

    def __init__(self, registry) -> None:
        self.registry = registry
        self._pending_by_session: dict[str, int] = {}
        self._active_subagents = 0
        self._guard_lock = asyncio.Lock()
        self._subagent_circuit_breaker = SubagentCircuitBreaker(
            failure_threshold=3,
            half_open_cooldown_s=60.0,
        )

    @property
    def max_depth(self) -> int:
        if bool(getattr(settings, "multi_agent_depth3_enabled", False)):
            return self.MAX_DEPTH_STAGE_B
        return self.MAX_DEPTH_STAGE_A

    @staticmethod
    def _session_key(request: AgentHandoffRequest) -> str:
        session_id = (
            str(getattr(request, "conversation_id", None) or "").strip()
            or str((getattr(request, "metadata", {}) or {}).get("session_id") or "").strip()
            or "unknown_session"
        )
        return session_id

    async def _reserve_capacity(self, request: AgentHandoffRequest) -> tuple[str, bool]:
        session_key = self._session_key(request)
        max_pending = max(1, int(getattr(settings, "max_pending_handoffs_per_session", 10)))
        max_subagents = max(1, int(getattr(settings, "max_concurrent_subagents_per_maya", 5)))
        target = str(getattr(request, "target_agent", "") or "").strip().lower()
        reserve_subagent = target in self.SUBAGENT_TARGETS

        async with self._guard_lock:
            pending = self._pending_by_session.get(session_key, 0)
            if pending >= max_pending:
                raise HandoffLimitError(
                    "handoff_session_queue_limit_exceeded",
                    f"pending handoffs exceeded for session {session_key}",
                )
            if reserve_subagent and self._active_subagents >= max_subagents:
                raise HandoffLimitError(
                    "handoff_subagent_concurrency_limit_exceeded",
                    "max concurrent subagents exceeded",
                )
            self._pending_by_session[session_key] = pending + 1
            if reserve_subagent:
                self._active_subagents += 1
                RuntimeMetrics.increment("subagent_active_count", 1)

        return session_key, reserve_subagent

    async def _release_capacity(self, session_key: str, reserved_subagent: bool) -> None:
        async with self._guard_lock:
            pending = self._pending_by_session.get(session_key, 0)
            if pending <= 1:
                self._pending_by_session.pop(session_key, None)
            else:
                self._pending_by_session[session_key] = pending - 1
            if reserved_subagent:
                self._active_subagents = max(0, self._active_subagents - 1)
                RuntimeMetrics.increment("subagent_active_count", -1)

    @staticmethod
    def _validate_mode_target(request: AgentHandoffRequest) -> None:
        target = str(request.target_agent or "").strip().lower()
        mode = str(request.execution_mode or "").strip().lower()
        if mode == "planning" and target not in {
            "planner",
            "project_manager",
            "team_coding",
            "team_review",
            "subagent_architect",
            "subagent_coder",
            "subagent_reviewer",
        }:
            raise HandoffValidationError("invalid_mode_target_combination")
        if mode == "background" and target == "system_operator":
            raise HandoffValidationError("background_system_operator_not_allowed")

    def validate_request(self, request: AgentHandoffRequest) -> None:
        if str(request.parent_agent or "").strip().lower() != "maya":
            logger.warning(
                "handoff_parent_blocked parent=%s target=%s handoff_id=%s trace_id=%s",
                request.parent_agent,
                request.target_agent,
                request.handoff_id,
                request.trace_id,
            )
            raise HandoffValidationError("parent_agent must be maya")

        if getattr(request, "target_agent", None) not in self.ALLOWED_TARGETS:
            raise HandoffValidationError(f"invalid target_agent: {getattr(request, 'target_agent', None)}")

        expected_depth = self.max_depth
        if getattr(request, "max_depth", None) != expected_depth:
            raise HandoffValidationError(f"max_depth must be {expected_depth}")

        if getattr(request, "delegation_depth", 0) >= getattr(request, "max_depth", 0):
            logger.warning(
                "handoff_depth_exceeded depth=%s max=%s handoff_id=%s trace_id=%s",
                getattr(request, "delegation_depth", 0),
                getattr(request, "max_depth", 0),
                request.handoff_id,
                request.trace_id,
            )
            raise HandoffValidationError("delegation depth exceeded")

        parent_handoff_id = getattr(request, "parent_handoff_id", None)
        depth_budget = int(getattr(request, "depth_budget", 1) or 1)
        depth_used = int(getattr(request, "depth_used", 0) or 0)
        if parent_handoff_id and parent_handoff_id == request.handoff_id:
            raise HandoffValidationError("invalid_handoff_lineage")
        if depth_budget <= 0:
            raise HandoffValidationError("invalid_depth_budget")
        if depth_used < 0:
            raise HandoffValidationError("invalid_depth_used")

        visited = set(str(x).strip().lower() for x in ((getattr(request, "metadata", {}) or {}).get("visited_targets") or []))
        target = str(getattr(request, "target_agent", "") or "").strip().lower()
        if target in visited:
            raise HandoffValidationError("handoff_cycle_detected")

        self._validate_mode_target(request)

        if request.execution_mode in {"background", "planning"} and not request.task_id:
            raise HandoffValidationError("task_id is required for background/planning handoffs")

    def consume_signal(self, signal: HandoffSignal) -> str:
        target = self.SIGNAL_TO_TARGET.get(signal.signal_name)
        if not target:
            raise HandoffValidationError(f"invalid handoff signal: {signal.signal_name}")
        logger.info("handoff_signal_consumed signal=%s target=%s", signal.signal_name, target)
        return target

    async def delegate(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        started = time.perf_counter()
        session_key = ""
        reserved_subagent = False
        target_key = str(getattr(request, "target_agent", "") or "").strip().lower()
        logger.info(
            "handoff_requested target=%s parent=%s active_agent=%s handoff_id=%s chain_id=%s",
            request.target_agent,
            request.parent_agent,
            request.active_agent,
            request.handoff_id,
            getattr(request, "delegation_chain_id", None) or request.handoff_id,
        )
        try:
            session_key, reserved_subagent = await self._reserve_capacity(request)
            if target_key in self.SUBAGENT_TARGETS and not self._subagent_circuit_breaker.can_call(target_key):
                raise HandoffLimitError(
                    "subagent_circuit_open",
                    f"subagent circuit open for target={target_key}",
                )
            self.validate_request(request)
            request.metadata = dict(request.metadata or {})
            visited_targets = [
                str(x).strip().lower()
                for x in (request.metadata.get("visited_targets") or [])
                if str(x).strip()
            ]
            current_target = str(request.target_agent or "").strip().lower()
            if current_target and current_target not in visited_targets:
                visited_targets.append(current_target)
            request.metadata["visited_targets"] = visited_targets
            match = await self.registry.can_accept(request)
            # Zero confidence is acceptable for explicit Maya-selected handoffs when
            # hard constraints passed. This typically happens on rewritten follow-up
            # turns where keyword matching is weak, but Maya has already chosen the
            # specialist target and the contract should remain observable.
            if match.confidence <= 0.0 and match.hard_constraints_passed:
                logger.info(
                    "handoff_zero_confidence_allowed target=%s handoff_id=%s reason=%s",
                    request.target_agent,
                    request.handoff_id,
                    match.reason,
                )
            logger.info(
                "handoff_accepted target=%s confidence=%.3f reason=%s handoff_id=%s",
                request.target_agent,
                match.confidence,
                match.reason,
                request.handoff_id,
            )
            result = await self.registry.handle(request)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "handoff_completed target=%s status=%s total_ms=%.2f handoff_id=%s",
                request.target_agent,
                result.status,
                elapsed_ms,
                request.handoff_id,
            )
            if target_key in self.SUBAGENT_TARGETS:
                self._subagent_circuit_breaker.record_success(target_key)
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            error_code = str(getattr(exc, "code", "") or exc.__class__.__name__)
            if target_key in self.SUBAGENT_TARGETS:
                circuit_state = self._subagent_circuit_breaker.record_failure(target_key)
                if circuit_state.value == "open":
                    RuntimeMetrics.increment("circuit_breaker_open_count")
                logger.warning(
                    "subagent_circuit_transition target=%s state=%s handoff_id=%s",
                    target_key,
                    circuit_state.value,
                    request.handoff_id,
                )
            logger.error(
                "handoff_failed target=%s error_code=%s fallback=maya total_ms=%.2f handoff_id=%s error=%s",
                request.target_agent,
                error_code,
                elapsed_ms,
                request.handoff_id,
                exc,
            )
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=request.target_agent,
                status="failed",
                user_visible_text=None,
                voice_text=None,
                structured_payload={},
                next_action="fallback_to_maya",
                error_code=error_code,
                error_detail=str(exc),
                metadata={"task_scope": "inline_untracked" if not request.task_id else "tracked"},
            )
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            RuntimeMetrics.observe("handoff_latency_ms", elapsed_ms)
            if session_key:
                await self._release_capacity(session_key, reserved_subagent)

def get_handoff_manager(registry) -> HandoffManager:
    return HandoffManager(registry)
