"""Centralized handoff validation and specialist delegation manager."""

from __future__ import annotations

import logging
import time

from core.agents.contracts import AgentHandoffRequest, AgentHandoffResult, HandoffSignal
from core.agents.subagent_manager import SubAgentLifecycleError, SubAgentManager
from core.agents.worktree_manager import WorktreeManager

logger = logging.getLogger(__name__)


class HandoffValidationError(ValueError):
    """Raised when a handoff request violates Phase 9A invariants."""


class HandoffLimitError(RuntimeError):
    """Raised when runtime handoff limits are exceeded."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class HandoffManager:
    MAX_DEPTH = 1
    MAX_SUBAGENT_FAILURES = 3
    ALLOWED_TARGETS = {
        "research",
        "system_operator",
        "planner",
        "media",
        "scheduling",
        "subagent_coder",
        "subagent_reviewer",
        "subagent_architect",
    }
    SUBAGENT_TARGETS = {
        "subagent_coder",
        "subagent_reviewer",
        "subagent_architect",
    }
    SIGNAL_TO_TARGET = {
        "transfer_to_research": "research",
        "transfer_to_system_operator": "system_operator",
        "transfer_to_planner": "planner",
        "transfer_to_media": "media",
        "transfer_to_scheduling": "scheduling",
        "transfer_to_subagent_coder": "subagent_coder",
        "transfer_to_subagent_reviewer": "subagent_reviewer",
        "transfer_to_subagent_architect": "subagent_architect",
    }

    def __init__(self, registry, *, subagent_manager: SubAgentManager | None = None) -> None:
        self.registry = registry
        self.subagent_manager = subagent_manager or SubAgentManager(
            worktree_manager=WorktreeManager(),
        )
        self._subagent_failure_counts: dict[str, int] = {}

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

    def handle_signal(self, signal: HandoffSignal) -> str:
        target = self.SIGNAL_TO_TARGET.get(signal.signal_name)
        if not target:
            raise HandoffValidationError(f"invalid handoff signal: {signal.signal_name}")
        logger.info("handoff_signal_consumed signal=%s target=%s", signal.signal_name, target)
        return target

    def consume_signal(self, signal: HandoffSignal) -> str:
        return self.handle_signal(signal)

    @staticmethod
    def _subagent_context(request: AgentHandoffRequest) -> dict:
        metadata = dict(request.metadata or {})
        parent_handoff_id = str(request.parent_handoff_id or request.handoff_id)
        delegation_chain_id = str(
            request.delegation_chain_id
            or metadata.get("delegation_chain_id")
            or f"chain_{request.handoff_id}"
        )
        return {
            "parent_handoff_id": parent_handoff_id,
            "delegation_chain_id": delegation_chain_id,
            "task_id": request.task_id,
            "trace_id": request.trace_id,
            "conversation_id": request.conversation_id,
            "base_branch": str(metadata.get("base_branch") or "HEAD"),
            "worktree_base": metadata.get("worktree_base"),
        }

    def _is_subagent_circuit_open(self, target: str) -> bool:
        return int(self._subagent_failure_counts.get(target, 0)) >= self.MAX_SUBAGENT_FAILURES

    def _record_subagent_failure(self, target: str) -> None:
        self._subagent_failure_counts[target] = int(self._subagent_failure_counts.get(target, 0)) + 1

    def _record_subagent_success(self, target: str) -> None:
        self._subagent_failure_counts[target] = 0

    async def _delegate_subagent(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        target = str(request.target_agent or "").strip().lower()
        if self._is_subagent_circuit_open(target):
            raise HandoffLimitError(
                "subagent_circuit_open",
                f"subagent circuit open for target={target}",
            )

        try:
            metadata = dict(request.metadata or {})
            spawned = await self.subagent_manager.spawn(
                target,
                self._subagent_context(request),
                worktree_path=metadata.get("worktree_path"),
            )
            self._record_subagent_success(target)
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=target,
                status="completed",
                user_visible_text=None,
                voice_text=None,
                structured_payload={
                    "subagent": spawned,
                    "runtime": "subagent_manager",
                },
                next_action="background" if request.execution_mode in {"background", "planning"} else "continue",
                metadata={
                    "task_scope": "tracked" if request.task_id else "inline_untracked",
                },
            )
        except Exception as exc:
            self._record_subagent_failure(target)
            code = exc.code if isinstance(exc, (SubAgentLifecycleError, HandoffLimitError)) else exc.__class__.__name__
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=target,
                status="failed",
                user_visible_text=None,
                voice_text=None,
                structured_payload={},
                next_action="fallback_to_maya",
                error_code=str(code),
                error_detail=str(exc),
                metadata={"task_scope": "tracked" if request.task_id else "inline_untracked"},
            )

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
            if str(request.target_agent or "").strip().lower() in self.SUBAGENT_TARGETS:
                result = await self._delegate_subagent(request)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                logger.info(
                    "handoff_completed target=%s status=%s total_ms=%.2f handoff_id=%s",
                    request.target_agent,
                    result.status,
                    elapsed_ms,
                    request.handoff_id,
                )
                return result
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
            error_code = exc.code if isinstance(exc, HandoffLimitError) else exc.__class__.__name__
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
                error_code=str(error_code),
                error_detail=str(exc),
                metadata={"task_scope": "inline_untracked" if not request.task_id else "tracked"},
            )

def get_handoff_manager(registry, *, subagent_manager: SubAgentManager | None = None) -> HandoffManager:
    return HandoffManager(registry, subagent_manager=subagent_manager)
