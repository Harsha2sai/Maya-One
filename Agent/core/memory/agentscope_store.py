"""P28 memory bridge: AgentScope working memory + SQLite persistence."""

from __future__ import annotations

import json
import inspect
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg


class MayaAgentScopeMemory:
    """
    Wrap AgentScope in-memory working memory with optional SQLite persistence.

    Runs in parallel to HybridMemoryManager during P28 migration.
    """

    def __init__(self, db_path: str, *, max_size: int = 200) -> None:
        self.db_path = str(db_path or "./dev_maya_one.db")
        self.short_term = InMemoryMemory()
        self._max_size = max(1, int(max_size))
        self._create_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _create_tables(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agentscope_memory (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    ts TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agentscope_memory_session_ts
                ON agentscope_memory(session_id, ts DESC);
                """
            )

    async def add(self, msg: Msg, persist: bool = False, session_id: Optional[str] = None) -> None:
        mark = str(session_id or "").strip() or None
        await self._maybe_await(self.short_term.add(msg, marks=mark, allow_duplicates=True))
        await self._trim_short_term_if_needed(mark=mark)
        if persist:
            await self._write_sqlite(msg, session_id=mark)

    async def add_many(
        self,
        messages: List[Msg],
        *,
        persist: bool = False,
        session_id: Optional[str] = None,
    ) -> None:
        for msg in messages or []:
            await self.add(msg, persist=persist, session_id=session_id)

    async def get_recent(self, k: int = 20, session_id: Optional[str] = None) -> List[Msg]:
        mark = str(session_id or "").strip() or None
        memories = list(
            await self._maybe_await(
                self.short_term.get_memory(mark=mark, prepend_summary=False),
            )
            or []
        )
        if k <= 0:
            return memories
        return memories[-int(k):]

    async def get_persisted(
        self,
        *,
        session_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Msg]:
        normalized_session = str(session_id or "").strip()
        sql = (
            "SELECT id, name, role, content, metadata, ts "
            "FROM agentscope_memory "
        )
        params: List[Any] = []
        if normalized_session:
            sql += "WHERE session_id = ? "
            params.append(normalized_session)
        sql += "ORDER BY ts DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        result: List[Msg] = []
        for row in reversed(rows):
            metadata = {}
            try:
                metadata = json.loads(str(row["metadata"] or "{}"))
            except Exception:
                metadata = {}
            result.append(
                Msg(
                    name=str(row["name"]),
                    role=str(row["role"]),
                    content=str(row["content"]),
                    metadata=metadata,
                    timestamp=str(row["ts"]),
                )
            )
        return result

    async def clear_short_term(self) -> None:
        await self._maybe_await(self.short_term.clear())

    async def _trim_short_term_if_needed(self, *, mark: Optional[str]) -> None:
        try:
            scoped = list(
                await self._maybe_await(
                    self.short_term.get_memory(mark=mark, prepend_summary=False),
                )
                or []
            )
            overflow = len(scoped) - self._max_size
            if overflow <= 0:
                return
            # Remove oldest overflow messages from this mark scope.
            remove_ids = [str(getattr(msg, "id", "")) for msg in scoped[:overflow] if getattr(msg, "id", None)]
            if remove_ids:
                await self._maybe_await(self.short_term.delete(remove_ids))
        except Exception:
            # Best-effort memory cap; never block runtime path.
            pass

    async def _write_sqlite(self, msg: Msg, *, session_id: Optional[str]) -> None:
        payload = msg.model_dump() if hasattr(msg, "model_dump") else dict(msg.__dict__)
        row_id = str(payload.get("id") or "")
        if not row_id:
            row_id = f"msg_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        ts = str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat())
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agentscope_memory
                (id, session_id, name, role, content, metadata, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    session_id,
                    str(payload.get("name") or "unknown"),
                    str(payload.get("role") or "assistant"),
                    str(payload.get("content") or ""),
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=True),
                    ts,
                ),
            )

    async def validate_parity(self, sample_sessions: int = 5) -> Dict[str, Any]:
        """
        Compare persisted and in-memory counts for up to N recent sessions.
        """
        limit = max(1, int(sample_sessions))
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT session_id, COUNT(*) AS persisted_count
                FROM agentscope_memory
                WHERE session_id IS NOT NULL AND session_id != ''
                GROUP BY session_id
                ORDER BY MAX(ts) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        session_results: List[Dict[str, Any]] = []
        parity_ok = True
        for row in rows:
            session_id = str(row["session_id"] or "").strip()
            persisted_count = int(row["persisted_count"] or 0)
            in_memory_count = len(
                await self._maybe_await(
                    self.short_term.get_memory(mark=session_id, prepend_summary=False),
                )
                or []
            )
            matched = in_memory_count >= persisted_count
            if not matched:
                parity_ok = False
            session_results.append(
                {
                    "session_id": session_id,
                    "persisted_count": persisted_count,
                    "in_memory_count": in_memory_count,
                    "matched": matched,
                }
            )

        return {
            "sampled_sessions": len(session_results),
            "sample_limit": limit,
            "parity_ok": parity_ok,
            "sessions": session_results,
        }

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value
