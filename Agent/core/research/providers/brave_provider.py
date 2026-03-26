from __future__ import annotations

import os

from core.research.base_provider import BaseSearchProvider
from core.research.research_models import SourceItem


class BraveProvider(BaseSearchProvider):
    name = "brave"
    api_key_env = "BRAVE_API_KEY"

    async def _search_impl(
        self,
        *,
        query: str,
        max_results: int,
        timeout_s: float,
    ) -> list[SourceItem]:
        api_key = os.getenv(self.api_key_env, "").strip()
        data = await self._get_json(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max(1, min(max_results, 10))},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            timeout_s=timeout_s,
        )

        results: list[SourceItem] = []
        for item in ((data.get("web") or {}).get("results") or [])[:max_results]:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            results.append(
                self._item(
                    title=str(item.get("title") or "Brave result"),
                    url=url,
                    snippet=str(item.get("description") or ""),
                )
            )
        return results
