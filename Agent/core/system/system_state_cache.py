from __future__ import annotations

import hashlib
import json
import logging

from .system_models import SystemAction

logger = logging.getLogger(__name__)


class SystemStateCache:
    _state: dict[str, bool] = {}

    @classmethod
    def fingerprint(cls, action: SystemAction) -> str:
        payload = f"{action.action_type.value}{json.dumps(action.params or {}, sort_keys=True)}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    @classmethod
    def already_done(cls, action: SystemAction) -> bool:
        fp = cls.fingerprint(action)
        if fp in cls._state:
            logger.info("system_state_cache_hit action=%s", action.action_type.value)
            return True
        return False

    @classmethod
    def record(cls, action: SystemAction) -> None:
        cls._state[cls.fingerprint(action)] = True

    @classmethod
    def clear(cls) -> None:
        cls._state.clear()
