from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List

from core.memory.memory_models import MemoryItem, MemorySource

if TYPE_CHECKING:
    from core.llm.smart_llm import SmartLLM
    from core.memory.hybrid_memory_manager import HybridMemoryManager

logger = logging.getLogger(__name__)


@dataclass
class DreamResult:
    skipped: bool = False
    skip_reason: str = ""
    compressed_count: int = 0
    summary_preview: str = ""
    session_id: str = ""


class DreamCycle:
    """
    Consolidate short-term conversational memories into durable summary memory.
    """

    MIN_ENTRIES = 5
    MAX_PREVIEW = 200

    def __init__(self, memory_manager: "HybridMemoryManager", llm: "SmartLLM"):
        self.memory = memory_manager
        self.llm = llm

    async def run(self, session_id: str, user_id: str) -> DreamResult:
        logger.info("dream_cycle_start session=%s user_id=%s", session_id, user_id)
        recent = await self._fetch_recent(session_id, user_id)
        if len(recent) < self.MIN_ENTRIES:
            return DreamResult(
                skipped=True,
                skip_reason=f"Only {len(recent)} entries (min {self.MIN_ENTRIES})",
                session_id=session_id,
            )

        summary = await self._compress(recent, session_id)
        await self._write_long_term(summary, session_id, user_id)
        cleared = await self._clear_short_term(session_id, user_id)

        logger.info(
            "dream_cycle_complete session=%s compressed=%s cleared=%s",
            session_id,
            len(recent),
            cleared,
        )

        preview = summary[: self.MAX_PREVIEW]
        if len(summary) > self.MAX_PREVIEW:
            preview += "..."
        return DreamResult(
            skipped=False,
            compressed_count=len(recent),
            summary_preview=preview,
            session_id=session_id,
        )

    async def _fetch_recent(self, session_id: str, user_id: str) -> List[str]:
        """
        Compatibility fetch path:
        - retrieve_session_memories/session method if present
        - fallback to keyword_search on session-scoped terms
        """
        if hasattr(self.memory, "retrieve_session_memories"):
            results = await self.memory.retrieve_session_memories(
                session_id=session_id,
                user_id=user_id,
                limit=100,
            )
            return [r.get("content", "") for r in results if r.get("content")]

        if hasattr(self.memory, "keyword_search"):
            results = await self.memory.keyword_search(
                query=f"session:{session_id}",
                user_id=user_id,
                limit=50,
            )
            return [r.get("content", "") for r in results if r.get("content")]

        retriever = getattr(self.memory, "retriever", None)
        if retriever and hasattr(retriever, "keyword_store"):
            results = retriever.keyword_store.keyword_search(
                query=f"session {session_id}",
                k=100,
                user_id=user_id,
                session_id=session_id,
            )
            return [r.get("text", "") for r in results if r.get("text")]

        return []

    async def _compress(self, entries: List[str], session_id: str) -> str:
        joined = "\n".join(f"- {e}" for e in entries)
        prompt = (
            "You are a memory consolidation assistant. "
            "Compress these entries into factual long-term memory. "
            "Keep facts, decisions, preferences, and completed tasks.\n\n"
            f"Session {session_id}:\n{joined}\n\n"
            "Compressed summary:"
        )

        generate = getattr(self.llm, "generate", None)
        if callable(generate):
            try:
                response = await generate(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                )
                return str(response).strip()
            except Exception as exc:
                logger.warning("dream_compress_failed session=%s error=%s", session_id, exc)

        return " | ".join(entries[:10])

    async def _write_long_term(self, summary: str, session_id: str, user_id: str) -> None:
        if hasattr(self.memory, "store"):
            await self.memory.store(
                content=f"[DreamSummary session={session_id}] {summary}",
                user_id=user_id,
                memory_type="long_term",
                metadata={"source": "dream_cycle", "session_id": session_id},
            )
            return

        memory_item = MemoryItem(
            text=f"[DreamSummary session={session_id}] {summary}",
            source=MemorySource.CONVERSATION,
            metadata={
                "source": "dream_cycle",
                "session_id": session_id,
                "user_id": user_id,
                "memory_type": "long_term",
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        retriever = getattr(self.memory, "retriever", None)
        if retriever is not None:
            retriever.add_memory(memory_item)

    async def _clear_short_term(self, session_id: str, user_id: str) -> int:
        if hasattr(self.memory, "clear_session"):
            return await self.memory.clear_session(session_id=session_id, user_id=user_id)

        # No clear API in this repo's HybridMemoryManager yet; keep summaries additive.
        return 0

