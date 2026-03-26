from __future__ import annotations

import re

from core.research.base_provider import BaseSearchProvider
from core.research.research_models import SourceItem


class WeatherProvider(BaseSearchProvider):
    name = "weather"
    api_key_env = None

    async def _search_impl(
        self,
        *,
        query: str,
        max_results: int,
        timeout_s: float,
    ) -> list[SourceItem]:
        city = self._extract_city(query)
        geo = await self._get_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout_s=timeout_s,
        )
        entries = geo.get("results") or []
        if not entries:
            return []
        first = entries[0]
        lat = first.get("latitude")
        lon = first.get("longitude")
        if lat is None or lon is None:
            return []

        weather = await self._get_json(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            timeout_s=timeout_s,
        )
        current = weather.get("current") or {}
        temperature = current.get("temperature_2m")
        wind = current.get("wind_speed_10m")
        humidity = current.get("relative_humidity_2m")
        code = current.get("weather_code")
        location_name = str(first.get("name") or city)
        temp_str = f"{temperature}°C" if temperature is not None else "N/A"
        wind_str = f"{wind} km/h" if wind is not None else "N/A"
        hum_str = f"{humidity}%" if humidity is not None else "N/A"
        summary = f"Temperature: {temp_str}, Wind: {wind_str}, Humidity: {hum_str}."
        source = self._item(
            title=f"Weather in {location_name}",
            url="https://open-meteo.com/",
            snippet=summary,
        )
        return [source]

    @staticmethod
    def _extract_city(query: str) -> str:
        q = str(query or "").strip()
        match = re.search(r"weather\s+(?:in|at)\s+([a-zA-Z\s]+)", q, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return q or "Hyderabad"
