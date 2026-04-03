from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.research.research_models import ProviderTask, SourceItem
from core.research.search_executor import SearchExecutor


class _FakeProvider:
    def __init__(self, items):
        self.items = items

    async def search(self, *_args, **_kwargs):
        return list(self.items)

    def is_configured(self):
        return False


@pytest.mark.asyncio
async def test_dedupes_results_by_url() -> None:
    executor = SearchExecutor()
    item1 = SourceItem.from_values(
        title="A",
        url="https://example.com/a?x=1",
        snippet="one",
        provider="tavily",
    )
    item2 = SourceItem.from_values(
        title="A2",
        url="https://example.com/a?x=2",
        snippet="two",
        provider="serper",
    )
    executor.providers = {"tavily": _FakeProvider([item1]), "serper": _FakeProvider([item2])}

    with patch("core.research.search_executor.web_search", new=AsyncMock(return_value={"results": []})):
        results = await executor.execute(
            [ProviderTask(provider="tavily", query="q"), ProviderTask(provider="serper", query="q")],
            "q",
        )

    assert len(results) == 1
    assert results[0].url.startswith("https://example.com/a")


@pytest.mark.asyncio
async def test_provider_exception_is_skipped() -> None:
    executor = SearchExecutor()
    bad_provider = SimpleNamespace(search=AsyncMock(side_effect=RuntimeError("boom")))
    good_item = SourceItem.from_values(
        title="B",
        url="https://example.com/b",
        snippet="ok",
        provider="good",
    )
    executor.providers = {
        "bad": bad_provider,
        "good": _FakeProvider([good_item]),
    }

    with patch("core.research.search_executor.web_search", new=AsyncMock(return_value={"results": []})):
        results = await executor.execute(
            [ProviderTask(provider="bad", query="q"), ProviderTask(provider="good", query="q")],
            "q",
        )

    assert len(results) == 1
    assert results[0].title == "B"


@pytest.mark.asyncio
async def test_fallback_web_search_when_low_source_count() -> None:
    executor = SearchExecutor()
    executor.providers = {"tavily": _FakeProvider([])}

    fallback_payload = {
        "results": [
            {
                "title": "Fallback",
                "url": "https://fallback.example/result",
                "snippet": "fallback snippet",
            }
        ]
    }

    with patch("core.research.search_executor.web_search", new=AsyncMock(return_value=fallback_payload)):
        results = await executor.execute([ProviderTask(provider="tavily", query="q")], "q")

    assert len(results) == 1
    assert results[0].provider == "web_search"


@pytest.mark.asyncio
async def test_missing_provider_is_skipped() -> None:
    executor = SearchExecutor()
    executor.providers = {}
    with patch("core.research.search_executor.web_search", new=AsyncMock(return_value={"results": []})):
        results = await executor.execute([ProviderTask(provider="missing", query="q")], "q")
    assert results == []


@pytest.mark.asyncio
async def test_low_confidence_fallback_returns_empty_when_no_premium_provider() -> None:
    executor = SearchExecutor()
    executor.providers = {"tavily": _FakeProvider([])}
    fallback_payload = {
        "results": [
            {
                "title": "Asking Alexandria",
                "url": "https://en.wikipedia.org/wiki/Asking_Alexandria",
                "snippet": "British rock band",
            }
        ]
    }

    with patch("core.research.search_executor.web_search", new=AsyncMock(return_value=fallback_payload)):
        results = await executor.execute(
            [ProviderTask(provider="tavily", query="iran market war")],
            "iran market war",
        )

    assert results == []
