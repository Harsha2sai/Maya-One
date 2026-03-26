"""
StepController controls execution of a single TaskStep.
TaskWorker calls this — does not embed retry/eval logic directly.

Flow:
StepController.run(step) -> execute tool with timeout -> evaluate result -> retry if needed -> replan if retry exhausted -> return final result
"""

import asyncio
import logging
from typing import Optional

from core.tasks.task_steps import TaskStep
from core.tasks.execution_evaluator import ExecutionEvaluator, ExecutionContext, ToolResult, StepEvaluation

logger = logging.getLogger(__name__)

STEP_MAX_RETRIES = 3

class StepExecutionFailed(Exception):
    """Raised when a step fails after all retries."""
    def __init__(self, step_title: str, reason: str):
        self.step_title = step_title
        self.reason = reason
        super().__init__(f"Step '{step_title}' failed: {reason}")

class StepNeedsReplan(Exception):
    """Raised when a step suggests replanning."""
    def __init__(self, step_title: str, reason: str):
        self.step_title = step_title
        self.reason = reason
        super().__init__(f"Step '{step_title}' needs replanning: {reason}")

class StepResult:
    """Result of step execution."""
    def __init__(self, success: bool, output: str, retry_count: int = 0):
        self.success = success
        self.output = output
        self.retry_count = retry_count

class StepController:
    """
    Controls execution of a single TaskStep.
    TaskWorker calls this — does not embed retry/eval logic directly.
    """

    def __init__(
        self,
        tool_executor,
        evaluator: ExecutionEvaluator,
        max_retries: int = STEP_MAX_RETRIES,
    ):
        self._executor = tool_executor
        self._evaluator = evaluator
        self._max_retries = max_retries

    async def run(
        self,
        step: TaskStep,
        context: ExecutionContext,
        retry_count: int = 0,
    ) -> StepResult:
        """
        Execute a step with evaluation and retry logic.

        Args:
            step: TaskStep to execute
            context: Execution context
            retry_count: Current retry attempt (internal use)

        Returns:
            StepResult with success status

        Raises:
            StepExecutionFailed: If step fails after retries
            StepNeedsReplan: If replanning is suggested
        """
        logger.info(f"Executing step: {step.description[:50]}")

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                self._executor(step.tool, step.parameters),
                timeout=step.step_timeout_seconds
            )
            tool_result = ToolResult(
                output=result if isinstance(result, str) else str(result),
                exit_code=0
            )
        except asyncio.TimeoutError:
            tool_result = ToolResult(
                output="",
                exit_code=-1,
                timed_out=True
            )
            logger.warning(f"Step '{step.description[:50]}' timed out after {step.step_timeout_seconds}s")
        except Exception as e:
            tool_result = ToolResult(
                output=str(e),
                exit_code=-1
            )
            logger.error(f"Step '{step.description[:50]}' execution error: {e}")

        # Evaluate the result
        evaluation = await self._evaluator.evaluate(step, tool_result, context)

        if evaluation.success:
            logger.info(f"Step '{step.description[:50]}' succeeded")
            return StepResult(success=True, output=tool_result.output)

        # Failed - handle retry logic
        if retry_count < self._max_retries and evaluation.suggested_retry:
            logger.warning(
                f"Step '{step.description[:50]}' failed (attempt {retry_count + 1}), retrying: {evaluation.reason}"
            )
            return await self.run(step, context, retry_count + 1)

        # Retry exhausted or not suggested
        if evaluation.suggested_replan:
            raise StepNeedsReplan(step.description, evaluation.reason)

        # Hard failure
        raise StepExecutionFailed(step.description, evaluation.reason)
