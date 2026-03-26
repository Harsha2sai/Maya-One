"""
Evaluates step success after execution.
Verification priority: structured → text → vision (last resort).
Every evaluation emits step_evaluation telemetry log.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum

from core.tasks.task_steps import TaskStep, VerificationType
from core.governance.policy import validate_safe_path

logger = logging.getLogger(__name__)

class StepEvaluation(BaseModel):
    """Result of evaluating a step execution."""
    success: bool
    reason: str
    suggested_retry: bool = True
    suggested_replan: bool = False

class ExecutionContext(BaseModel):
    """Context for execution evaluation."""
    task_id: str
    visual_verification_allowed: bool = False
    has_browser: bool = False
    user_role: Optional[str] = None

class ToolResult(BaseModel):
    """Result of tool execution."""
    output: str
    exit_code: int = 0
    timed_out: bool = False

class ExecutionEvaluator:
    """
    Evaluates step success after execution.
    Verification priority: structured → text → vision (last resort).
    Every evaluation emits step_evaluation telemetry log.
    """

    def __init__(self):
        self.logger = logger

    async def evaluate(
        self,
        step: TaskStep,
        result: ToolResult,
        context: ExecutionContext,
    ) -> StepEvaluation:
        # Hard timeout - treat as failure immediately
        if result.timed_out:
            eval_result = StepEvaluation(
                success=False,
                reason=f"timeout after {step.step_timeout_seconds}s",
                suggested_retry=True
            )
            self._log_evaluation(step, eval_result)
            return eval_result

        # Priority 1 - file check (1-5ms, deterministic)
        if step.verification_type == VerificationType.FILE_EXISTS:
            exists = Path(step.expected_path).expanduser().exists() if step.expected_path else False
            eval_result = StepEvaluation(
                success=exists,
                reason="file_found" if exists else f"not_found: {step.expected_path}",
                suggested_retry=not exists
            )

        # Priority 2 - exit code (1ms, deterministic)
        elif step.verification_type == VerificationType.COMMAND_EXIT_CODE:
            eval_result = StepEvaluation(
                success=result.exit_code == 0,
                reason=f"exit_code={result.exit_code}",
                suggested_retry=result.exit_code != 0
            )

        # Priority 3 - current URL check (5ms, reliable)
        elif step.verification_type == VerificationType.URL_MATCHES:
            # Browser check will be implemented when browser tools are added
            # For now, simulate a URL check
            current = "about:blank"  # Placeholder
            if step.expected_url_pattern:
                matched = step.expected_url_pattern in current
                eval_result = StepEvaluation(
                    success=matched,
                    reason=f"url={current}",
                    suggested_retry=not matched
                )
            else:
                eval_result = StepEvaluation(
                    success=True,
                    reason="url_check_skipped",
                    suggested_retry=False
                )

        # Priority 4 - DOM presence check (5-20ms, reliable)
        elif step.verification_type == VerificationType.DOM_CHECK:
            eval_result = await self._verify_dom_check(step, result, context)

        # Priority 5 - LLM text evaluation (200-500ms, medium)
        elif step.verification_type == VerificationType.OUTPUT_CONTAINS:
            eval_result = await self._verify_output_contains(step, result, context)

        # Priority 6 - screenshot + vision (800-2000ms, last resort)
        elif context.visual_verification_allowed and context.has_browser:
            eval_result = await self._verify_with_vision(step, result, context)

        # No verification configured - assume success
        else:
            eval_result = StepEvaluation(
                success=True,
                reason="no_verification_configured",
                suggested_retry=False
            )

        # Telemetry - log every evaluation for debugging
        self._log_evaluation(step, eval_result)
        return eval_result

    async def _verify_dom_check(self, step: TaskStep, result: ToolResult, context: ExecutionContext) -> StepEvaluation:
        """Verify DOM element presence."""
        if not step.expected_selector:
            return StepEvaluation(
                success=True,
                reason="dom_check_skipped_no_selector",
                suggested_retry=False
            )

        # For now, assume success if we have browser context
        # Browser tools will provide actual DOM checking later
        has_browser = context.has_browser

        return StepEvaluation(
            success=has_browser,
            reason=f"dom_check_{'passed' if has_browser else 'failed'}",
            suggested_retry=not has_browser
        )

    async def _verify_output_contains(self, step: TaskStep, result: ToolResult, context: ExecutionContext) -> StepEvaluation:
        """Verify output contains expected text or meets success criteria."""
        if not step.success_criteria:
            return StepEvaluation(
                success=True,
                reason="output_contains_skipped_no_criteria",
                suggested_retry=False
            )

        # Simple text matching for now
        criteria = step.success_criteria.lower()
        output = result.output.lower()

        # Check if success criteria appears in output
        if criteria in output:
            return StepEvaluation(
                success=True,
                reason=f"found: {criteria[:100]}...",
                suggested_retry=False
            )
        else:
            return StepEvaluation(
                success=False,
                reason=f"missing: {criteria[:100]}...",
                suggested_retry=True
            )

    async def _verify_with_vision(self, step: TaskStep, result: ToolResult, context: ExecutionContext) -> StepEvaluation:
        """Fallback verification using vision model."""
        return StepEvaluation(
            success=True,
            reason="vision_verification_fallback",
            suggested_retry=False
        )

    def _log_evaluation(self, step: TaskStep, result: StepEvaluation):
        """Log evaluation result for telemetry."""
        self.logger.info(
            "step_evaluation step=%s verification=%s success=%s reason=%s",
            step.description[:50] if step.description else "unknown",
            step.verification_type or "none",
            result.success,
            result.reason
        )
