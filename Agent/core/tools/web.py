"""
Web Tools Contracts + Runtime Wrappers for Phase 4.

WebSearch and WebFetch tools for internet access.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from core.research.research_models import SourceItem
from core.research.research_planner import ResearchPlanner
from core.research.result_synthesizer import ResultSynthesizer
from core.research.search_executor import SearchExecutor
from tools.information import web_search as legacy_web_search

logger = logging.getLogger(__name__)


class SearchResult(BaseModel):
    """A single web search result."""
    title: str
    url: str
    snippet: str
    source: Optional[str] = None
    published_date: Optional[datetime] = None
    relevance_score: Optional[float] = None


class WebSearchRequest(BaseModel):
    """Request to perform a web search."""
    query: str = Field(description="Search query")
    num_results: int = Field(default=10, ge=1, le=50)
    recency_days: Optional[int] = None  # Limit to recent results
    site_filter: Optional[str] = None   # e.g., "site:github.com"
    safe_search: bool = True


class WebSearchResult(BaseModel):
    """Result of a web search."""
    success: bool
    results: List[SearchResult] = Field(default_factory=list)
    query: str = ""
    result_count: int = 0
    search_time_ms: Optional[int] = None
    error: Optional[str] = None


class WebFetchRequest(BaseModel):
    """Request to fetch a web page."""
    url: str = Field(description="URL to fetch")
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    extract_text: bool = True      # Extract main text content
    extract_links: bool = False    # Extract all links
    extract_images: bool = False   # Extract image URLs
    follow_redirects: bool = True
    headers: Dict[str, str] = Field(default_factory=dict)


class WebFetchResult(BaseModel):
    """Result of fetching a web page."""
    success: bool
    url: str
    status_code: Optional[int] = None
    content: Optional[str] = None
    title: Optional[str] = None
    extracted_text: Optional[str] = None
    links: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)
    content_type: Optional[str] = None
    fetch_time_ms: Optional[int] = None
    error: Optional[str] = None
    truncated: bool = False  # If content exceeded max size


def _effective_query(query: str, site_filter: Optional[str]) -> str:
    q = str(query or "").strip()
    site = str(site_filter or "").strip()
    if not site:
        return q
    if site.startswith("site:"):
        return f"{q} {site}"
    return f"{q} site:{site}"


def _relevance_score(query: str, title: str, snippet: str, url: str) -> float:
    terms = {token for token in re.findall(r"[a-z0-9]+", str(query or "").lower()) if len(token) > 1}
    if not terms:
        return 1.0
    haystack = set(re.findall(r"[a-z0-9]+", f"{title} {snippet} {url}".lower()))
    overlap = len(terms.intersection(haystack))
    return round(float(overlap) / float(max(1, len(terms))), 3)


async def web_search(
    query: str,
    max_results: int = 10,
    *,
    recency_days: Optional[int] = None,
    site_filter: Optional[str] = None,
    safe_search: bool = True,
) -> WebSearchResult:
    """
    Run web search through the existing research planner/executor pipeline.
    Falls back to legacy DDGS path if provider routing fails.
    """
    started = time.perf_counter()
    resolved_query = _effective_query(query, site_filter)
    limit = max(1, min(int(max_results or 10), 50))
    _ = safe_search  # Reserved for future provider-level enforcement.
    _ = recency_days  # Reserved for provider-level recency filtering.

    try:
        planner = ResearchPlanner(role_llm=None)
        executor = SearchExecutor()
        plan = await planner.plan(resolved_query)
        sources = await executor.execute(plan.tasks, plan.fallback_query or resolved_query)

        results = [
            SearchResult(
                title=source.title,
                url=source.url,
                snippet=source.snippet,
                source=source.provider,
                relevance_score=_relevance_score(resolved_query, source.title, source.snippet, source.url),
            )
            for source in sources[:limit]
        ]
        elapsed_ms = int((time.perf_counter() - started) * 1000.0)
        return WebSearchResult(
            success=True,
            results=results,
            query=resolved_query,
            result_count=len(results),
            search_time_ms=elapsed_ms,
        )
    except Exception as exc:
        logger.warning("web_search_pipeline_failed query=%s error=%s", resolved_query, exc)

    # Fallback path: legacy DDGS/Tavily-compatible tool function.
    try:
        payload = await legacy_web_search(None, resolved_query)
        raw_results = list((payload or {}).get("results") or [])[:limit]
        results = [
            SearchResult(
                title=str(item.get("title") or "Web Result"),
                url=str(item.get("url") or item.get("href") or ""),
                snippet=str(item.get("snippet") or item.get("body") or ""),
                source=str(item.get("source") or item.get("provider") or "web_search"),
                relevance_score=_relevance_score(
                    resolved_query,
                    str(item.get("title") or ""),
                    str(item.get("snippet") or item.get("body") or ""),
                    str(item.get("url") or item.get("href") or ""),
                ),
            )
            for item in raw_results
            if str(item.get("url") or item.get("href") or "").strip()
        ]
        elapsed_ms = int((time.perf_counter() - started) * 1000.0)
        return WebSearchResult(
            success=True,
            results=results,
            query=resolved_query,
            result_count=len(results),
            search_time_ms=elapsed_ms,
        )
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000.0)
        return WebSearchResult(
            success=False,
            results=[],
            query=resolved_query,
            result_count=0,
            search_time_ms=elapsed_ms,
            error=f"web search failed: {exc}",
        )


async def fetch_page(
    url: str,
    *,
    timeout_seconds: int = 30,
    extract_text: bool = True,
    extract_links: bool = False,
    extract_images: bool = False,
    follow_redirects: bool = True,
    headers: Optional[Dict[str, str]] = None,
    max_content_chars: int = 200_000,
) -> WebFetchResult:
    """Fetch and parse web page content with optional extraction flags."""
    started = time.perf_counter()
    resolved_url = str(url or "").strip()
    if not resolved_url:
        return WebFetchResult(success=False, url="", error="url is required")

    timeout = aiohttp.ClientTimeout(total=max(1, int(timeout_seconds or 30)))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                resolved_url,
                headers=dict(headers or {}),
                allow_redirects=bool(follow_redirects),
            ) as response:
                body = await response.text(errors="ignore")
                content_type = str(response.headers.get("content-type") or "")
                status_code = int(response.status)
                final_url = str(response.url)
    except asyncio.TimeoutError:
        return WebFetchResult(
            success=False,
            url=resolved_url,
            error="timeout fetching page",
            fetch_time_ms=int((time.perf_counter() - started) * 1000.0),
        )
    except Exception as exc:
        return WebFetchResult(
            success=False,
            url=resolved_url,
            error=f"fetch failed: {exc}",
            fetch_time_ms=int((time.perf_counter() - started) * 1000.0),
        )

    soup = BeautifulSoup(body, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else None
    text_content: Optional[str] = None
    links: List[str] = []
    images: List[str] = []

    if extract_text:
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        lines = [line.strip() for line in soup.get_text(separator="\n", strip=True).splitlines() if line.strip()]
        text_content = "\n".join(lines)

    if extract_links:
        links = [
            str(anchor.get("href") or "").strip()
            for anchor in soup.find_all("a")
            if str(anchor.get("href") or "").strip()
        ]

    if extract_images:
        images = [
            str(img.get("src") or "").strip()
            for img in soup.find_all("img")
            if str(img.get("src") or "").strip()
        ]

    truncated = False
    content = body
    if len(content) > int(max_content_chars):
        content = content[: int(max_content_chars)]
        truncated = True
    if text_content is not None and len(text_content) > int(max_content_chars):
        text_content = text_content[: int(max_content_chars)]
        truncated = True

    return WebFetchResult(
        success=200 <= status_code < 400,
        url=final_url,
        status_code=status_code,
        content=content,
        title=title,
        extracted_text=text_content,
        links=links,
        images=images,
        content_type=content_type,
        fetch_time_ms=int((time.perf_counter() - started) * 1000.0),
        error=None if 200 <= status_code < 400 else f"http status {status_code}",
        truncated=truncated,
    )


async def summarize_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search + summarization helper for concise downstream consumption.
    Uses existing research synthesizer and falls back to deterministic summary.
    """
    search_result = await web_search(query=query, max_results=max_results)
    if not search_result.success:
        return {
            "success": False,
            "query": query,
            "summary": "",
            "voice_summary": "",
            "results": [],
            "error": search_result.error,
        }

    sources = [
        SourceItem.from_values(
            title=item.title,
            url=item.url,
            snippet=item.snippet,
            provider=item.source or "web_search",
        )
        for item in search_result.results
    ]

    role_llm = None
    try:
        from core.runtime.global_agent import GlobalAgentContainer

        role_llm = getattr(GlobalAgentContainer, "_smart_llm", None)
    except Exception:
        role_llm = None

    synthesizer = ResultSynthesizer(role_llm=role_llm)
    summary, voice_summary = await synthesizer.synthesize(query, sources)
    return {
        "success": True,
        "query": query,
        "summary": summary,
        "voice_summary": voice_summary,
        "result_count": search_result.result_count,
        "results": [item.model_dump() for item in search_result.results],
    }
