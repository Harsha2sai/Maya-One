"""
Web Tools Contracts for Phase 4

WebSearch and WebFetch tools for internet access.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


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
