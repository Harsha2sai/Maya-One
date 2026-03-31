from __future__ import annotations

import time
from typing import Any

import pytest

from core.memory.hybrid_retriever import HybridRetriever


class _FakeVectorStore:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.last_query: tuple[str, int, dict[str, Any] | None] | None = None

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.last_query = (query, k, filter)
        filtered = self.records
        if filter and filter.get("user_id"):
            filtered = [
                r for r in filtered if (r.get("metadata") or {}).get("user_id") == filter["user_id"]
            ]
        elif filter and "$and" in filter:
            clauses = list(filter.get("$and") or [])
            for clause in clauses:
                if "user_id" in clause:
                    filtered = [
                        r for r in filtered if (r.get("metadata") or {}).get("user_id") == clause["user_id"]
                    ]
                if "session_id" in clause:
                    filtered = [
                        r for r in filtered if (r.get("metadata") or {}).get("session_id") == clause["session_id"]
                    ]
        return filtered[:k]

    def add_memory(self, memory: Any) -> bool:
        return True

    def delete_memory(self, memory_id: str) -> bool:
        return True


class _FakeKeywordStore:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.last_query: tuple[str, int, str | None] | None = None

    def keyword_search(
        self,
        query: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self.last_query = (query, k, user_id)
        filtered = self.records
        if user_id:
            filtered = [
                r for r in filtered if (r.get("metadata") or {}).get("user_id") == user_id
            ]
        if session_id:
            filtered = [
                r for r in filtered if (r.get("metadata") or {}).get("session_id") == session_id
            ]
        return filtered[:k]

    def add_memory(self, memory: Any) -> bool:
        return True

    def delete_memory(self, memory_id: str) -> bool:
        return True


def _sample_records() -> list[dict[str, Any]]:
    return [
        {"id": "a1", "text": "alpha from user a", "metadata": {"user_id": "user_A", "session_id": "sess_A"}},
        {"id": "b1", "text": "beta from user b", "metadata": {"user_id": "user_B", "session_id": "sess_B"}},
        {"id": "a2", "text": "alpha second", "metadata": {"user_id": "user_A", "session_id": "sess_A"}},
    ]


def _build_retriever(records: list[dict[str, Any]] | None = None) -> tuple[HybridRetriever, _FakeVectorStore, _FakeKeywordStore]:
    dataset = records or _sample_records()
    vector_store = _FakeVectorStore(dataset)
    keyword_store = _FakeKeywordStore(dataset)
    retriever = HybridRetriever(vector_store=vector_store, keyword_store=keyword_store)
    return retriever, vector_store, keyword_store


def test_retrieve_with_user_id_filters_results() -> None:
    retriever, _, _ = _build_retriever()
    results = retriever.retrieve("alpha", user_id="user_A")
    assert results
    assert all((r.get("metadata") or {}).get("user_id") == "user_A" for r in results)


def test_retrieve_with_session_id_pushes_combined_filter_to_vector_store() -> None:
    retriever, vector_store, _ = _build_retriever()
    results = retriever.retrieve("alpha", user_id="user_A", session_id="sess_A")
    assert results
    assert vector_store.last_query is not None
    filter_arg = vector_store.last_query[2]
    assert filter_arg == {"$and": [{"user_id": "user_A"}, {"session_id": "sess_A"}]}
    assert all((r.get("metadata") or {}).get("session_id") == "sess_A" for r in results)


def test_retrieve_without_user_id_returns_all() -> None:
    retriever, _, _ = _build_retriever()
    results = retriever.retrieve("alpha", user_id=None)
    user_ids = {(r.get("metadata") or {}).get("user_id") for r in results}
    assert "user_A" in user_ids
    assert "user_B" in user_ids


def test_retrieve_voice_origin_caps_k(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_RETRIEVER_K", "3")
    monkeypatch.setenv("VOICE_RETRIEVER_K_VECTOR", "4")
    monkeypatch.setenv("VOICE_RETRIEVER_K_KEYWORD", "4")

    retriever, vector_store, keyword_store = _build_retriever()
    results = retriever.retrieve(
        "alpha",
        k=10,
        k_vector=10,
        k_keyword=10,
        user_id="user_A",
        origin="voice",
    )

    assert vector_store.last_query is not None
    assert keyword_store.last_query is not None
    assert vector_store.last_query[1] == 4
    assert keyword_store.last_query[1] == 4
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_retrieve_async_timeout_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever, _, _ = _build_retriever()
    monkeypatch.setenv("VOICE_RETRIEVER_TIMEOUT_S", "0.05")

    def slow_retrieve(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        time.sleep(0.2)
        return [{"id": "late", "text": "late", "metadata": {"user_id": "user_A"}}]

    monkeypatch.setattr(retriever, "retrieve", slow_retrieve)
    result = await retriever.retrieve_async("alpha", user_id="user_A", origin="voice")
    assert result == []


@pytest.mark.asyncio
async def test_retrieve_async_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever, _, _ = _build_retriever()

    def failing_retrieve(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(retriever, "retrieve", failing_retrieve)
    result = await retriever.retrieve_async("alpha", user_id="user_A", origin="chat")
    assert result == []


def test_retrieve_logs_no_user_scope_warning(caplog: pytest.LogCaptureFixture) -> None:
    retriever, _, _ = _build_retriever()
    with caplog.at_level("WARNING"):
        retriever.retrieve("weather", origin="voice", user_id=None)
    assert "memory_retrieve_no_user_scope" in caplog.text


@pytest.mark.asyncio
async def test_retrieve_async_voice_uses_short_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever, _, _ = _build_retriever()
    monkeypatch.setenv("VOICE_RETRIEVER_TIMEOUT_S", "0.05")
    monkeypatch.setenv("RETRIEVER_TIMEOUT_S", "2.0")

    def slow_retrieve(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        time.sleep(0.15)
        return [{"id": "late", "text": "late", "metadata": {"user_id": "user_A"}}]

    monkeypatch.setattr(retriever, "retrieve", slow_retrieve)
    started = time.perf_counter()
    result = await retriever.retrieve_async("x", user_id="user_A", origin="voice")
    elapsed = time.perf_counter() - started

    assert result == []
    assert elapsed < 0.2


@pytest.mark.asyncio
async def test_retrieve_async_chat_uses_long_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever, _, _ = _build_retriever()
    monkeypatch.setenv("VOICE_RETRIEVER_TIMEOUT_S", "0.05")
    monkeypatch.setenv("RETRIEVER_TIMEOUT_S", "0.4")

    def slow_retrieve(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        time.sleep(0.15)
        return [{"id": "ok", "text": "ok", "metadata": {"user_id": "user_A"}}]

    monkeypatch.setattr(retriever, "retrieve", slow_retrieve)
    result = await retriever.retrieve_async("x", user_id="user_A", origin="chat")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_retrieve_with_scope_fallback_uses_user_scope_when_session_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    retriever, _, _ = _build_retriever()
    with caplog.at_level("INFO"):
        results = await retriever.retrieve_with_scope_fallback(
            query="alpha",
            user_id="user_A",
            session_id="missing_session",
            origin="voice",
            k=5,
        )

    assert results
    assert all((r.get("metadata") or {}).get("user_id") == "user_A" for r in results)
    assert "retriever_scope_fallback reason=session_scoped_empty" in caplog.text


@pytest.mark.asyncio
async def test_retrieve_with_scope_fallback_keeps_session_scope_when_hits_exist(
    caplog: pytest.LogCaptureFixture,
) -> None:
    retriever, _, _ = _build_retriever()
    with caplog.at_level("INFO"):
        results = await retriever.retrieve_with_scope_fallback(
            query="alpha",
            user_id="user_A",
            session_id="sess_A",
            origin="voice",
            k=5,
        )

    assert results
    assert all((r.get("metadata") or {}).get("session_id") == "sess_A" for r in results)
    assert "retriever_scope_fallback reason=session_scoped_empty" not in caplog.text


def test_retriever_sanitizes_fts_special_tokens_before_keyword_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever, _, keyword_store = _build_retriever()
    monkeypatch.setattr("core.memory.hybrid_retriever.sanitize_fts_query", lambda _q: "hyderabad weather")

    retriever.retrieve("what is AND OR", user_id="user_A")

    assert keyword_store.last_query is not None
    assert keyword_store.last_query[0] == "hyderabad weather"


def test_retriever_skips_keyword_search_when_sanitized_query_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever, _, keyword_store = _build_retriever()
    monkeypatch.setattr("core.memory.hybrid_retriever.sanitize_fts_query", lambda _q: None)

    retriever.retrieve("what is AND OR", user_id="user_A")

    assert keyword_store.last_query is None
