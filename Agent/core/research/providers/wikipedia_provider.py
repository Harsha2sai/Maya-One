from __future__ import annotations

import os

from core.research.base_provider import BaseSearchProvider
from core.research.research_models import SourceItem


class WikipediaProvider(BaseSearchProvider):
    name = "wikipedia"
    api_key_env = None

    async def _search_impl(
        self,
        *,
        query: str,
        max_results: int,
        timeout_s: float,
    ) -> list[SourceItem]:
        user_agent = str(
            os.getenv(
                "WIKIPEDIA_USER_AGENT",
                "Maya-One/1.0 (https://maya-one.local; contact=ops@maya-one.local)",
            )
        ).strip()
        data = await self._get_json(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "format": "json",
                "utf8": 1,
                "srsearch": query,
                "srlimit": max(1, min(max_results, 10)),
            },
            headers={"User-Agent": user_agent},
            timeout_s=timeout_s,
        )
        results: list[SourceItem] = []
        for item in (data.get("query") or {}).get("search", [])[:max_results]:
            title = str(item.get("title") or "Wikipedia")
            page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            snippet = str(item.get("snippet") or "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
            results.append(self._item(title=title, url=page_url, snippet=snippet))
        return results
