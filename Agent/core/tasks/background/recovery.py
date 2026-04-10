"""Crash-recovery coordinator for recoverable background tasks."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .executor import BackgroundExecutor


class RecoveryManager:
    """Resumes recoverable background tasks discovered in persistence."""

    def __init__(self, *, persistence: Any, executor: BackgroundExecutor, user_id: Optional[str] = None) -> None:
        self._persistence = persistence
        self._executor = executor
        self._default_user_id = str(user_id or "").strip() or None

    async def recover(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        recover_fn = getattr(self._persistence, "recover_background_tasks", None)
        if not callable(recover_fn):
            return []

        resolved_user_id = str(user_id or self._default_user_id or "").strip() or None
        recovered_items = await recover_fn(resolved_user_id)

        resumed: List[Dict[str, Any]] = []
        for item in recovered_items or []:
            resumed_state = await self._executor.resume_task(dict(item or {}))
            if resumed_state is not None:
                resumed.append(resumed_state)
        return resumed
