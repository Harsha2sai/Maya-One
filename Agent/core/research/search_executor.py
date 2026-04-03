from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse, urlunparse

from tools.information import web_search

from .providers import (
    BraveProvider,
    FinanceProvider,
    GeoProvider,
    NewsProvider,
    SerperProvider,
    TavilyProvider,
    WeatherProvider,
    WikipediaProvider,
)
from .research_models import ProviderTask, SourceItem

logger = logging.getLogger(__name__)


class SearchExecutor:
    _PREMIUM_PROVIDER_NAMES = ("tavily", "serper", "brave", "news")
    _RELEVANCE_STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "be",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "latest",
        "news",
        "of",
        "on",
        "or",
        "search",
        "the",
        "to",
        "what",
        "with",
    }

    def __init__(self) -> None:
        self.provider_timeout_s = float(os.getenv("RESEARCH_PROVIDER_TIMEOUT_S", "8.0"))
        self.providers = {
            "tavily": TavilyProvider(),
            "serper": SerperProvider(),
            "brave": BraveProvider(),
            "wikipedia": WikipediaProvider(),
            "weather": WeatherProvider(),
            "news": NewsProvider(),
            "finance": FinanceProvider(),
            "geo": GeoProvider(),
        }

    async def execute(self, tasks: list[ProviderTask], query: str) -> list[SourceItem]:
        if not tasks:
            return await self._fallback_web_search(query)

        premium_provider_ready = self.has_configured_premium_provider()
        merged: list[SourceItem] = []
        attempted: set[str] = set()
        for task in tasks:
            attempted.add(task.provider)
            merged.extend(await self._run_task(task))

        deduped = self._dedupe_sources(merged)

        # Guaranteed backup path: if planner omitted Tavily and results are thin,
        # try Tavily before generic web_search fallback.
        if len(deduped) < 2 and "tavily" not in attempted:
            tavily = self.providers.get("tavily")
            if tavily is not None:
                logger.info("research_provider_fallback_attempt provider=tavily query=%s", query)
                tavily_results = await tavily.search(
                    query,
                    max_results=4,
                    timeout_s=self.provider_timeout_s,
                )
                deduped = self._dedupe_sources([*deduped, *tavily_results])

        if len(deduped) < 2:
            fallback = await self._fallback_web_search(query)
            deduped = self._dedupe_sources([*deduped, *fallback])

        if not premium_provider_ready and not self._has_query_relevance(query, deduped):
            logger.warning(
                "research_low_confidence_missing_provider query=%s deduped_count=%s",
                query,
                len(deduped),
            )
            return []

        return deduped

    def has_configured_premium_provider(self) -> bool:
        for provider_name in self._PREMIUM_PROVIDER_NAMES:
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            is_configured = getattr(provider, "is_configured", None)
            if callable(is_configured):
                try:
                    if bool(is_configured()):
                        return True
                except Exception:
                    continue
        return False

    async def _run_task(self, task: ProviderTask) -> list[SourceItem]:
        provider = self.providers.get(task.provider)
        if provider is None:
            logger.warning("research_provider_missing provider=%s", task.provider)
            return []
        logger.info(
            "research_provider_attempt provider=%s query=%s max_results=%s",
            task.provider,
            task.query,
            task.max_results,
        )
        try:
            results = await provider.search(
                task.query,
                max_results=task.max_results,
                timeout_s=self.provider_timeout_s,
            )
        except Exception as exc:
            logger.warning(
                "research_provider_exception provider=%s query=%s error=%s",
                task.provider,
                task.query,
                exc,
            )
            return []
        logger.info(
            "research_provider_done provider=%s result_count=%s",
            task.provider,
            len(results),
        )
        return results

    async def _fallback_web_search(self, query: str) -> list[SourceItem]:
        try:
            payload = await web_search(None, query)
        except Exception as e:
            logger.warning("research_fallback_web_search_failed query=%s error=%s", query, e)
            return []

        results: list[SourceItem] = []
        for item in (payload or {}).get("results", []):
            url = str(item.get("url") or item.get("href") or "").strip()
            if not url:
                continue
            results.append(
                SourceItem.from_values(
                    title=str(item.get("title") or "Web result"),
                    url=url,
                    snippet=str(item.get("snippet") or item.get("body") or ""),
                    provider="web_search",
                )
            )
        return results

    @staticmethod
    def _normalized_url(url: str) -> str:
        parsed = urlparse(str(url or "").strip())
        if not parsed.scheme:
            return ""
        clean = parsed._replace(query="", fragment="")
        return urlunparse(clean).rstrip("/").lower()

    def _dedupe_sources(self, sources: list[SourceItem]) -> list[SourceItem]:
        seen: set[str] = set()
        deduped: list[SourceItem] = []
        for source in sources:
            normalized = self._normalized_url(source.url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(source)
        return deduped

    @classmethod
    def _relevance_terms(cls, text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]+", str(text or "").lower())
        return [
            token
            for token in tokens
            if len(token) >= 2 and token not in cls._RELEVANCE_STOPWORDS
        ]

    @classmethod
    def _has_query_relevance(cls, query: str, sources: list[SourceItem]) -> bool:
        query_terms = set(cls._relevance_terms(query))
        if not query_terms:
            return True
        for source in sources:
            haystack_terms = set(
                cls._relevance_terms(
                    f"{source.title} {source.snippet} {source.url} {source.domain}"
                )
            )
            if haystack_terms.intersection(query_terms):
                return True
        return False
