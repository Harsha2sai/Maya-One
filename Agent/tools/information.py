import logging
import asyncio
import os
import re
import requests
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
from livekit.agents import function_tool, RunContext

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CONDITIONS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "icy fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight showers",
    81: "moderate showers",
    82: "violent showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}
_GEO_CACHE: dict[str, tuple[float, float, str, str]] = {}
_CITY_COORD_OVERRIDES: dict[str, tuple[float, float, str, str]] = {
    # Common/local defaults to avoid geocoding latency on hot paths.
    "hyderabad": (17.38405, 78.45636, "Hyderabad", "India"),
}
_SEARCH_RELEVANCE_STOPWORDS = {
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

try:
    from ddgs import DDGS as _DDGS
except Exception:
    try:
        from duckduckgo_search import DDGS as _DDGS
    except Exception:
        _DDGS = None


def _wmo_condition(code: object) -> str:
    """Return a human-readable weather condition for a WMO code."""
    try:
        code_int = int(code)
    except Exception:
        return "unknown conditions"
    return WMO_CONDITIONS.get(code_int, "unknown conditions")


def _relevance_terms(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return [
        token
        for token in tokens
        if len(token) >= 2 and token not in _SEARCH_RELEVANCE_STOPWORDS
    ]


def _has_query_relevance(query: str, structured_results: list[dict[str, str]]) -> bool:
    query_terms = set(_relevance_terms(query))
    if not query_terms:
        return True

    for item in structured_results:
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "")
        url = str(item.get("url") or "")
        haystack_terms = set(_relevance_terms(f"{title} {snippet} {url}"))
        if haystack_terms.intersection(query_terms):
            return True
    return False


def _fallback_web_search_sync(query: str, max_results: int) -> list[dict[str, str]]:
    """
    Lightweight fallback search via DuckDuckGo Instant Answer endpoint.
    Returns normalized result objects compatible with web_search output.
    """
    timeout = (
        float(os.getenv("WEB_SEARCH_FALLBACK_CONNECT_TIMEOUT_S", "2.0")),
        float(os.getenv("WEB_SEARCH_FALLBACK_READ_TIMEOUT_S", "5.0")),
    )
    resp = requests.get(
        "https://api.duckduckgo.com/",
        params={
            "q": query,
            "format": "json",
            "no_html": "1",
            "no_redirect": "1",
            "skip_disambig": "1",
        },
        timeout=timeout,
        headers={"User-Agent": "Maya-One/1.0"},
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload if isinstance(payload, dict) else {}

    structured: list[dict[str, str]] = []

    abstract_url = str(data.get("AbstractURL") or "").strip()
    abstract_text = str(data.get("AbstractText") or "").strip()
    heading = str(data.get("Heading") or "").strip() or "DuckDuckGo Result"
    if abstract_url:
        structured.append(
            {
                "title": heading,
                "url": abstract_url,
                "snippet": abstract_text,
            }
        )

    related_topics = data.get("RelatedTopics") or []
    for topic in related_topics:
        if len(structured) >= max_results:
            break
        if isinstance(topic, dict) and isinstance(topic.get("Topics"), list):
            for sub in topic["Topics"]:
                if len(structured) >= max_results:
                    break
                if not isinstance(sub, dict):
                    continue
                url = str(sub.get("FirstURL") or "").strip()
                text = str(sub.get("Text") or "").strip()
                if not url:
                    continue
                structured.append(
                    {
                        "title": text[:120] or "DuckDuckGo Topic",
                        "url": url,
                        "snippet": text,
                    }
                )
            continue
        if not isinstance(topic, dict):
            continue
        url = str(topic.get("FirstURL") or "").strip()
        text = str(topic.get("Text") or "").strip()
        if not url:
            continue
        structured.append(
            {
                "title": text[:120] or "DuckDuckGo Topic",
                "url": url,
                "snippet": text,
            }
        )

    if structured:
        return structured[:max_results]

    # News-focused fallback: Google News RSS search.
    lowered = str(query or "").lower()
    if any(token in lowered for token in ("news", "latest", "today", "this week")):
        news_resp = requests.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            timeout=timeout,
            headers={"User-Agent": "Maya-One/1.0"},
        )
        news_resp.raise_for_status()
        root = ET.fromstring(news_resp.text)
        for item in root.findall(".//item"):
            if len(structured) >= max_results:
                break
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            if not link:
                continue
            structured.append(
                {
                    "title": title or "News result",
                    "url": link,
                    "snippet": description,
                }
            )
        if structured:
            return structured[:max_results]

    # Secondary fallback: Wikipedia opensearch for broad informational queries.
    wiki_resp = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "opensearch",
            "search": query,
            "limit": max_results,
            "namespace": "0",
            "format": "json",
        },
        timeout=timeout,
        headers={"User-Agent": "Maya-One/1.0"},
    )
    wiki_resp.raise_for_status()
    wiki_payload = wiki_resp.json()
    if (
        isinstance(wiki_payload, list)
        and len(wiki_payload) >= 4
        and isinstance(wiki_payload[1], list)
        and isinstance(wiki_payload[2], list)
        and isinstance(wiki_payload[3], list)
    ):
        titles = wiki_payload[1]
        snippets = wiki_payload[2]
        urls = wiki_payload[3]
        for idx, title in enumerate(titles):
            if len(structured) >= max_results:
                break
            url = str(urls[idx] if idx < len(urls) else "").strip()
            if not url:
                continue
            snippet = str(snippets[idx] if idx < len(snippets) else "").strip()
            structured.append(
                {
                    "title": str(title or "Wikipedia Result"),
                    "url": url,
                    "snippet": snippet,
                }
            )

    return structured[:max_results]


def _get_weather_sync(city: str) -> str:
    """
    Fetch weather using Open-Meteo geocoding + forecast.
    This function runs in a worker thread via asyncio.to_thread.
    """
    connect_timeout_s = float(os.getenv("WEATHER_CONNECT_TIMEOUT_S", "1.5"))
    read_timeout_s = float(os.getenv("WEATHER_READ_TIMEOUT_S", "3.0"))
    timeout = (connect_timeout_s, read_timeout_s)

    cache_key = city.strip().lower()
    cached = _GEO_CACHE.get(cache_key) or _CITY_COORD_OVERRIDES.get(cache_key)
    if cached:
        lat, lon, location_name, country = cached
        _GEO_CACHE.setdefault(cache_key, cached)
    else:
        try:
            geo_resp = requests.get(
                GEOCODING_URL,
                params={"name": city, "count": 1, "language": "en", "format": "json"},
                timeout=timeout,
                headers={"User-Agent": "Maya-One/1.0"},
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
        except Exception as e:
            logger.warning("Weather geocoding failed for %s: %s", city, e)
            return f"I couldn't find the location for {city}."

        results = geo_data.get("results") if isinstance(geo_data, dict) else None
        if not results:
            return f"I couldn't find a location matching {city}."

        location = results[0] or {}
        lat = location.get("latitude")
        lon = location.get("longitude")
        if lat is None or lon is None:
            return f"I couldn't find a location matching {city}."

        location_name = str(location.get("name") or city).strip()
        country = str(location.get("country") or "").strip()
        _GEO_CACHE[cache_key] = (float(lat), float(lon), location_name, country)

    try:
        wx_resp = requests.get(
            WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
                "temperature_unit": "celsius",
                "windspeed_unit": "kmh",
            },
            timeout=timeout,
            headers={"User-Agent": "Maya-One/1.0"},
        )
        wx_resp.raise_for_status()
        wx_data = wx_resp.json()
    except Exception as e:
        logger.warning("Weather forecast fetch failed for %s: %s", city, e)
        return f"I couldn't fetch weather for {city} right now. Please try again."

    current = wx_data.get("current_weather", {}) if isinstance(wx_data, dict) else {}
    temp = current.get("temperature")
    wind = current.get("windspeed")
    if wind is None:
        wind = current.get("wind_speed_10m")
    condition = _wmo_condition(current.get("weathercode", current.get("weather_code")))

    if temp is None:
        return f"Weather data for {city} is unavailable right now."

    location_part = f"{location_name}, {country}" if country else location_name
    if wind is None:
        return f"Currently {condition} in {location_part}. {temp} degrees Celsius."
    return f"Currently {condition} in {location_part}. {temp} degrees Celsius, wind {wind} kilometers per hour."


@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    """Get current weather for a city using Open-Meteo."""
    city_name = (city or "").strip() or "Hyderabad"
    connect_timeout_s = float(os.getenv("WEATHER_CONNECT_TIMEOUT_S", "1.5"))
    read_timeout_s = float(os.getenv("WEATHER_READ_TIMEOUT_S", "3.0"))
    overall_timeout_s = max(1.0, connect_timeout_s + read_timeout_s + 1.0)

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_get_weather_sync, city_name),
            timeout=overall_timeout_s,
        )
    except asyncio.TimeoutError:
        logger.warning("Weather lookup timed out for %s (overall_timeout_s=%.2f)", city_name, overall_timeout_s)
        return f"I couldn't fetch weather for {city_name} right now. Please try again."
    except Exception as e:
        logger.error(f"Weather lookup failed for {city_name}: {e}")
        return f"Weather lookup failed for {city_name}."

@function_tool(name="web_search")
async def web_search(context: RunContext, query: str) -> dict:
    """Search the web using DuckDuckGo."""
    search_timeout_s = max(3.0, float(os.getenv("WEB_SEARCH_TIMEOUT_S", "12.0")))
    fallback_timeout_s = max(2.0, float(os.getenv("WEB_SEARCH_FALLBACK_TIMEOUT_S", "6.0")))
    max_results = max(1, int(os.getenv("WEB_SEARCH_MAX_RESULTS", "3")))
    fallback_url = f"https://duckduckgo.com/?q={quote_plus(query)}"

    try:
        if _DDGS is None:
            fallback = await asyncio.wait_for(
                asyncio.to_thread(_fallback_web_search_sync, query, max_results),
                timeout=fallback_timeout_s,
            )
            if fallback:
                return {"results": fallback, "query": query, "source": "fallback_duckduckgo_instant"}
            return {
                "error": "search_unavailable",
                "results": [],
                "message": "DuckDuckGo search library unavailable.",
                "fallback_url": fallback_url,
            }

        def _search():
            with _DDGS() as ddgs:
                backend = str(os.getenv("WEB_SEARCH_BACKEND", "lite")).strip()
                if backend:
                    try:
                        return list(ddgs.text(query, max_results=max_results, backend=backend))
                    except TypeError:
                        # Backward compatibility for DDGS variants without backend kwarg.
                        return list(ddgs.text(query, max_results=max_results))
                return list(ddgs.text(query, max_results=max_results))
        
        results = await asyncio.wait_for(asyncio.to_thread(_search), timeout=search_timeout_s)
        
        if results:
            structured = []
            for r in results:
                structured.append(
                    {
                        "title": r.get("title", "No title"),
                        "url": r.get("href", r.get("url", "")),
                        "snippet": r.get("body", ""),
                    }
                )
            if not _has_query_relevance(query, structured):
                logger.info(
                    "Search results discarded as irrelevant for query '%s' (%s candidates)",
                    query,
                    len(structured),
                )
                return {
                    "success": False,
                    "error": "irrelevant_results",
                    "results": [],
                    "query": query,
                    "message": "I couldn't find anything relevant for that search.",
                }
                logger.info(f"Search results for '{query}': {len(results)} found")
            return {
                "results": structured,
                "query": query,
            }
        return {"results": [], "query": query, "message": "No results found"}
    except asyncio.TimeoutError:
        logger.warning("Web search timed out for '%s' (timeout_s=%.1f)", query, search_timeout_s)
        try:
            fallback = await asyncio.wait_for(
                asyncio.to_thread(_fallback_web_search_sync, query, max_results),
                timeout=fallback_timeout_s,
            )
            if fallback:
                return {"results": fallback, "query": query, "source": "fallback_duckduckgo_instant"}
        except Exception as fallback_err:
            logger.warning("Fallback web search failed for '%s': %s", query, fallback_err)
        return {
            "error": "timeout",
            "results": [],
            "message": "Search timed out.",
            "fallback_url": fallback_url,
        }
    except Exception as e:
        logger.error(f"Error searching the web for '{query}': {e}")
        try:
            fallback = await asyncio.wait_for(
                asyncio.to_thread(_fallback_web_search_sync, query, max_results),
                timeout=fallback_timeout_s,
            )
            if fallback:
                return {"results": fallback, "query": query, "source": "fallback_duckduckgo_instant"}
        except Exception as fallback_err:
            logger.warning("Fallback web search failed after error for '%s': %s", query, fallback_err)
        return {
            "error": "search_failed",
            "results": [],
            "message": f"An error occurred while searching the web for '{query}'.",
            "fallback_url": fallback_url,
        }
