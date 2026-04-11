"""P28 A2A foundation adapter."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from agentscope.server import AgentServerLauncher as _AgentServerLauncher  # type: ignore
except Exception:
    _AgentServerLauncher = None


class MayaA2AServer:
    """
    Maya adapter for AgentScope A2A server lifecycle.

    This is intentionally a foundation stub for P28.
    Full production wiring is deferred to later phases.
    """

    def __init__(
        self,
        agent_name: str,
        host: str = "localhost",
        port: int = 12000,
    ) -> None:
        self.agent_name = str(agent_name or "maya").strip() or "maya"
        self.host = str(host or "localhost").strip() or "localhost"
        self.port = int(port)
        self._launcher: Any = None
        self._started = False

        if _AgentServerLauncher is None:
            logger.info("maya_a2a_launcher_unavailable status=stub_only")
            return

        try:
            self._launcher = _AgentServerLauncher(
                host=self.host,
                port=self.port,
                agent_class_name=self.agent_name,
            )
        except Exception as exc:
            logger.warning("maya_a2a_launcher_init_failed error=%s", exc)
            self._launcher = None

    async def start(self) -> bool:
        if self._launcher is None:
            return False
        try:
            launch = getattr(self._launcher, "launch", None)
            if callable(launch):
                maybe = launch()
                if inspect.isawaitable(maybe):
                    await maybe
                self._started = True
                return True
        except Exception as exc:
            logger.warning("maya_a2a_start_failed error=%s", exc)
        return False

    async def stop(self) -> bool:
        if self._launcher is None:
            return False
        try:
            shutdown = getattr(self._launcher, "shutdown", None)
            if callable(shutdown):
                maybe = shutdown()
                if inspect.isawaitable(maybe):
                    await maybe
                self._started = False
                return True
        except Exception as exc:
            logger.warning("maya_a2a_stop_failed error=%s", exc)
        return False

    @property
    def started(self) -> bool:
        return self._started

    @property
    def available(self) -> bool:
        return self._launcher is not None


__all__ = ["MayaA2AServer"]
