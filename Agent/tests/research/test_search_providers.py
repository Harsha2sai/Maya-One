from __future__ import annotations

from unittest.mock import patch

import pytest

from core.research.providers import (
    BraveProvider,
    FinanceProvider,
    GeoProvider,
    NewsProvider,
    SerperProvider,
    TavilyProvider,
    WeatherProvider,
    WikipediaProvider,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_cls,env_key",
    [
        (TavilyProvider, "TAVILY_API_KEY"),
        (SerperProvider, "SERPER_API_KEY"),
        (BraveProvider, "BRAVE_API_KEY"),
        (NewsProvider, "NEWSAPI_API_KEY"),
        (FinanceProvider, "ALPHA_VANTAGE_API_KEY"),
    ],
)
async def test_keyed_provider_skips_without_api_key(provider_cls, env_key, monkeypatch):
    monkeypatch.delenv(env_key, raising=False)
    provider = provider_cls()
    results = await provider.search("test query")
    assert results == []


@pytest.mark.asyncio
async def test_keyless_providers_report_configured() -> None:
    assert WikipediaProvider().is_configured() is True
    assert WeatherProvider().is_configured() is True
    assert GeoProvider().is_configured() is True


@pytest.mark.asyncio
async def test_wikipedia_provider_normalizes_results() -> None:
    provider = WikipediaProvider()
    payload = {
        "query": {
            "search": [
                {
                    "title": "Maya",
                    "snippet": "Assistant details",
                }
            ]
        }
    }
    with patch.object(provider, "_get_json", return_value=payload):
        results = await provider.search("maya", max_results=1)

    assert len(results) == 1
    assert results[0].domain == "en.wikipedia.org"
    assert results[0].provider == "wikipedia"


@pytest.mark.asyncio
async def test_wikipedia_provider_sets_user_agent_header() -> None:
    provider = WikipediaProvider()
    payload = {"query": {"search": []}}

    with patch.object(provider, "_get_json", return_value=payload) as mocked_get_json:
        await provider.search("maya", max_results=1)

    _, kwargs = mocked_get_json.call_args
    headers = kwargs.get("headers") or {}
    assert "User-Agent" in headers
    assert str(headers["User-Agent"]).strip() != ""
