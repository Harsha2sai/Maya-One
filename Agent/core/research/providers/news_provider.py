from __future__ import annotations

import os

from core.research.base_provider import BaseSearchProvider
from core.research.research_models import SourceItem


class NewsProvider(BaseSearchProvider):
    name = "news"
    api_key_env = "NEWSAPI_API_KEY"

    async def _search_impl(
        self,
        *,
        query: str,
        max_results: int,
        timeout_s: float,
    ) -> list[SourceItem]:
        api_key = os.getenv(self.api_key_env, "").strip()
        data = await self._get_json(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "pageSize": max(1, min(max_results, 10)),
                "sortBy": "publishedAt",
                "language": "en",
                "apiKey": api_key,
            },
            timeout_s=timeout_s,
        )

        results: list[SourceItem] = []
        for article in (data.get("articles") or [])[:max_results]:
            url = str(article.get("url") or "").strip()
            if not url:
                continue
            results.append(
                self._item(
                    title=str(article.get("title") or "News result"),
                    url=url,
                    snippet=str(article.get("description") or article.get("content") or ""),
                )
            )
        return results
