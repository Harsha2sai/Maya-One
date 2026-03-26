from __future__ import annotations

import asyncio
from typing import Any

import pytest
import requests

from tools import information as info


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


def test_get_weather_returns_temperature_and_condition(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        if "geocoding-api.open-meteo.com" in url:
            return _FakeResponse(
                {
                    "results": [
                        {
                            "name": "Hyderabad",
                            "country": "India",
                            "latitude": 17.38,
                            "longitude": 78.48,
                        }
                    ]
                }
            )
        return _FakeResponse(
            {"current_weather": {"temperature": 29.0, "windspeed": 14.0, "weathercode": 2}}
        )

    monkeypatch.setattr(info.requests, "get", fake_get)
    result = info._get_weather_sync("Hyderabad")
    assert "Currently partly cloudy in Hyderabad, India." in result
    assert "29.0 degrees Celsius" in result
    assert "wind 14.0 kilometers per hour" in result


def test_get_weather_geocoding_failure_returns_safe_string(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        raise requests.RequestException("dns failure")

    monkeypatch.setattr(info.requests, "get", fake_get)
    result = info._get_weather_sync("Nowhere")
    assert "couldn't find the location" in result.lower()


def test_get_weather_geocoding_empty_results_returns_safe_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        if "geocoding-api.open-meteo.com" in url:
            return _FakeResponse({"results": []})
        raise AssertionError("weather endpoint should not be called when geocoding is empty")

    monkeypatch.setattr(info.requests, "get", fake_get)
    result = info._get_weather_sync("UnknownCity")
    assert "couldn't find a location matching" in result.lower()


def test_get_weather_weather_api_failure_returns_safe_string(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        if "geocoding-api.open-meteo.com" in url:
            return _FakeResponse(
                {"results": [{"name": "Hyderabad", "latitude": 17.38, "longitude": 78.48}]}
            )
        raise requests.RequestException("weather api down")

    monkeypatch.setattr(info.requests, "get", fake_get)
    result = info._get_weather_sync("Hyderabad")
    assert "couldn't fetch weather for hyderabad" in result.lower()


@pytest.mark.asyncio
async def test_get_weather_timeout_returns_safe_string(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(2.0)
        return func(*args, **kwargs)

    monkeypatch.setattr(info.asyncio, "to_thread", slow_to_thread)
    monkeypatch.setenv("WEATHER_CONNECT_TIMEOUT_S", "0.1")
    monkeypatch.setenv("WEATHER_READ_TIMEOUT_S", "0.1")
    result = await info.get_weather(None, city="Hyderabad")
    assert "couldn't fetch weather for hyderabad" in result.lower()


def test_wmo_condition_known_and_unknown() -> None:
    assert info._wmo_condition(63) == "moderate rain"
    assert info._wmo_condition(999) == "unknown conditions"


@pytest.mark.asyncio
async def test_web_search_returns_safe_message_when_results_are_irrelevant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDDGS:
        def __enter__(self) -> "FakeDDGS":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
            return False

        def text(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
            return [
                {
                    "title": "Range lookup issue in spreadsheet",
                    "href": "https://example.com/spreadsheet-range-lookup",
                    "body": "It is not returning the correct value and skips arguments.",
                }
            ]

    monkeypatch.setattr(info, "_DDGS", FakeDDGS)
    result = await info.web_search(None, query="xkq99zz7")

    assert result.get("success") is False
    assert result.get("error") == "irrelevant_results"
    assert result.get("results") == []
    assert result.get("message") == "I couldn't find anything relevant for that search."


@pytest.mark.asyncio
async def test_web_search_keeps_relevant_results(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDDGS:
        def __enter__(self) -> "FakeDDGS":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
            return False

        def text(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
            return [
                {
                    "title": "Latest AI news and model updates",
                    "href": "https://example.com/ai-news",
                    "body": "Top AI launches and research updates this week.",
                }
            ]

    monkeypatch.setattr(info, "_DDGS", FakeDDGS)
    result = await info.web_search(None, query="latest ai news")

    assert result.get("query") == "latest ai news"
    assert isinstance(result.get("results"), list)
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Latest AI news and model updates"
    assert result.get("success") is not False
