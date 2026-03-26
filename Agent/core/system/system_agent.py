from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from .confirmation_gate import ConfirmationGate
from .rate_limiter import SystemRateLimiter
from .screenshot_limiter import ScreenshotLimiter
from .system_models import SystemResult
from .system_planner import SystemPlanner
from .system_state_cache import SystemStateCache

logger = logging.getLogger(__name__)


class SystemAgent:
    def __init__(self) -> None:
        self.planner = SystemPlanner()

    async def run(
        self,
        *,
        intent: str,
        user_id: str,
        session_id: str,
        session: Any,
        trace_id: str,
        publish_confirmation_required: Callable[[Any, Any], Awaitable[None]] | None = None,
    ) -> SystemResult:
        del user_id, session_id
        try:
            ScreenshotLimiter.reset(trace_id)
            SystemStateCache.clear()
            SystemRateLimiter.reset_task()
            ConfirmationGate.set_publisher(publish_confirmation_required)

            return await self.planner.plan_and_execute(intent, session=session, trace_id=trace_id)
        except Exception as exc:
            logger.error("system_agent_error trace_id=%s error=%s", trace_id, exc, exc_info=True)
            from .system_models import SystemActionType

            return SystemResult(
                success=False,
                action_type=SystemActionType.VISION_QUERY,
                message="Something went wrong with that system action.",
                detail=str(exc),
                trace_id=trace_id,
            )
