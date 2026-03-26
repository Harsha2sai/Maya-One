"""Centralized handoff validation and specialist delegation manager."""

from __future__ import annotations

import logging
import time
from core.agents.contracts import AgentHandoffRequest, AgentHandoffResult, HandoffSignal

logger = logging.getLogger(__name__)


class HandoffValidationError(ValueError):
    """Raised when a handoff request violates Phase 9A invariants."""


class HandoffManager:
    MAX_DEPTH = 1
    ALLOWED_TARGETS = {"research", "system_operator", "planner", "media", "scheduling"}
    SIGNAL_TO_TARGET = {
        "transfer_to_research": "research",
        "transfer_to_system_operator": "system_operator",
        "transfer_to_planner": "planner",
        "transfer_to_media": "media",
        "transfer_to_scheduling": "scheduling",
    }

    def __init__(self, registry) -> None:
        self.registry = registry

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

        if request.target_agent not in self.ALLOWED_TARGETS:
            raise HandoffValidationError(f"invalid target_agent: {request.target_agent}")

        if request.max_depth != self.MAX_DEPTH:
            raise HandoffValidationError(f"max_depth must be {self.MAX_DEPTH}")

        if request.delegation_depth >= request.max_depth:
            logger.warning(
                "handoff_depth_exceeded depth=%s max=%s handoff_id=%s trace_id=%s",
                request.delegation_depth,
                request.max_depth,
                request.handoff_id,
                request.trace_id,
            )
            raise HandoffValidationError("delegation depth exceeded")

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
        logger.info(
            "handoff_requested target=%s parent=%s active_agent=%s handoff_id=%s",
            request.target_agent,
            request.parent_agent,
            request.active_agent,
            request.handoff_id,
        )
        try:
            self.validate_request(request)
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
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.error(
                "handoff_failed target=%s error_code=%s fallback=maya total_ms=%.2f handoff_id=%s error=%s",
                request.target_agent,
                exc.__class__.__name__,
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
                error_code=exc.__class__.__name__,
                error_detail=str(exc),
                metadata={"task_scope": "inline_untracked" if not request.task_id else "tracked"},
            )

def get_handoff_manager(registry) -> HandoffManager:
    return HandoffManager(registry)
