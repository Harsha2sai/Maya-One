from __future__ import annotations

from core.research.base_provider import BaseSearchProvider
from core.research.research_models import SourceItem


class GeoProvider(BaseSearchProvider):
    name = "geo"
    api_key_env = None

    async def _search_impl(
        self,
        *,
        query: str,
        max_results: int,
        timeout_s: float,
    ) -> list[SourceItem]:
        q = str(query or "").lower()
        if "my location" not in q and "where am i" not in q:
            return []

        data = await self._get_json("http://ip-api.com/json", timeout_s=timeout_s)
        city = data.get("city")
        region = data.get("regionName")
        country = data.get("country")
        if not city and not country:
            return []

        summary = f"Approximate location: {city}, {region}, {country}."
        return [
            self._item(
                title="IP geolocation",
                url="http://ip-api.com/",
                snippet=summary,
            )
        ]
