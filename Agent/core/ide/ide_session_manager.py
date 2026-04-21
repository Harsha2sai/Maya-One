from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import time
from pathlib import Path
from typing import Optional
from uuid import uuid4

import logging

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IDESession:
    session_id: str
    workspace_path: str
    user_id: str
    created_at: str
    created_at_epoch_s: float
    status: str


class MaxSessionsExceededError(RuntimeError):
    """Raised when concurrent IDE session limit is exceeded."""


class SessionNotFoundError(KeyError):
    """Raised when an IDE session id is not found."""


class IDESessionManager:
    def __init__(
        self,
        max_concurrent: int = 5,
        session_ttl_seconds: int = 1800,
        cleanup_interval_seconds: int = 60,
        audit_store=None,  # IDEAuditStore; optional persistence
    ) -> None:
        self._sessions: dict[str, IDESession] = {}
        self._max_concurrent = max(1, int(max_concurrent))
        self._session_ttl_seconds = max(1, int(session_ttl_seconds))
        self._cleanup_interval_seconds = max(1, int(cleanup_interval_seconds))
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._shutdown_event = asyncio.Event()
        self._audit_store = audit_store
        self._rehydrated = False

    def _evict_expired_sessions(self) -> int:
        now_s = time.time()
        expired: list[str] = []
        for session_id, session in self._sessions.items():
            if session.status != "open":
                expired.append(session_id)
                continue
            age_s = now_s - float(session.created_at_epoch_s)
            if age_s >= self._session_ttl_seconds:
                expired.append(session_id)
        for session_id in expired:
            self._sessions.pop(session_id, None)
            if self._audit_store is not None:
                self._audit_store.remove_session(session_id)
        return len(expired)

    def _rehydrate_from_store(self) -> int:
        if self._rehydrated or self._audit_store is None:
            return 0

        restored = 0
        for row in self._audit_store.get_open_sessions():
            try:
                workspace = Path(str(row.get("workspace_path") or "")).expanduser().resolve()
            except Exception:
                continue
            if not workspace.exists() or not workspace.is_dir():
                self._audit_store.remove_session(str(row.get("session_id") or ""))
                continue

            created_at_epoch_s = float(row.get("created_at_epoch_s") or 0.0)
            if created_at_epoch_s <= 0:
                self._audit_store.remove_session(str(row.get("session_id") or ""))
                continue

            age_s = time.time() - created_at_epoch_s
            if age_s >= self._session_ttl_seconds:
                self._audit_store.remove_session(str(row.get("session_id") or ""))
                continue

            if len(self._sessions) >= self._max_concurrent:
                break

            session_id = str(row.get("session_id") or "").strip()
            if not session_id:
                continue

            self._sessions[session_id] = IDESession(
                session_id=session_id,
                workspace_path=str(workspace),
                user_id=str(row.get("user_id") or "unknown"),
                created_at=str(row.get("created_at") or datetime.now(timezone.utc).isoformat()),
                created_at_epoch_s=created_at_epoch_s,
                status="open",
            )
            restored += 1

        self._rehydrated = True
        if restored:
            logger.info("ide_session_rehydrated count=%s", restored)
        return restored

    async def _cleanup_loop(self) -> None:
        try:
            while not self._shutdown_event.is_set():
                await asyncio.sleep(self._cleanup_interval_seconds)
                removed = self._evict_expired_sessions()
                if removed:
                    logger.info("ide_session_cleanup_evicted count=%s", removed)
        except asyncio.CancelledError:
            return

    async def start_cleanup(self) -> None:
        self._rehydrate_from_store()
        if self._cleanup_task and not self._cleanup_task.done():
            return
        self._shutdown_event.clear()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup(self) -> None:
        self._shutdown_event.set()
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self._cleanup_task = None

    def open_session(self, workspace_path: str, user_id: str) -> IDESession:
        self._rehydrate_from_store()
        self._evict_expired_sessions()
        active_count = sum(1 for s in self._sessions.values() if s.status == "open")
        if active_count >= self._max_concurrent:
            raise MaxSessionsExceededError(
                f"Maximum concurrent IDE sessions reached ({self._max_concurrent})"
            )

        workspace = Path(workspace_path).expanduser().resolve()
        if not workspace.exists() or not workspace.is_dir():
            raise ValueError(f"Invalid workspace_path: {workspace_path}")

        session = IDESession(
            session_id=f"ide_{uuid4().hex}",
            workspace_path=str(workspace),
            user_id=str(user_id or "unknown"),
            created_at=datetime.now(timezone.utc).isoformat(),
            created_at_epoch_s=time.time(),
            status="open",
        )
        self._sessions[session.session_id] = session
        if self._audit_store is not None:
            self._audit_store.write_session(asdict(session))
        return session

    def close_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.status = "closed"
        self._sessions.pop(session_id, None)
        if self._audit_store is not None:
            self._audit_store.remove_session(session_id)
        return True

    def get_session(self, session_id: str) -> Optional[IDESession]:
        self._rehydrate_from_store()
        self._evict_expired_sessions()
        return self._sessions.get(session_id)

    def require_session(self, session_id: str) -> IDESession:
        session = self.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return session
