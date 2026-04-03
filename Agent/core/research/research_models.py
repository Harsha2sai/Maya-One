from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
from urllib.parse import urlparse


@dataclass
class SourceItem:
    title: str
    url: str
    domain: str
    snippet: str
    provider: str

    @classmethod
    def from_values(
        cls,
        *,
        title: str,
        url: str,
        snippet: str,
        provider: str,
    ) -> "SourceItem":
        parsed = urlparse(str(url or "").strip())
        domain = (parsed.netloc or "").replace("www.", "").strip() or "unknown"
        return cls(
            title=str(title or "Source").strip() or "Source",
            url=str(url or "").strip(),
            domain=domain,
            snippet=str(snippet or "").strip(),
            provider=str(provider or "unknown").strip() or "unknown",
        )

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
            "provider": self.provider,
        }


@dataclass
class ProviderTask:
    provider: str
    query: str
    max_results: int = 5


@dataclass
class ResearchPlan:
    tasks: List[ProviderTask] = field(default_factory=list)
    fallback_query: str = ""


@dataclass
class ResearchResult:
    summary: str
    sources: List[SourceItem]
    query: str
    trace_id: str
    duration_ms: int
    voice_summary: str = ""
    voice_mode: str = "brief"

    def to_event_payload(self) -> dict:
        return {
            "summary": self.summary,
            "query": self.query,
            "sources": [source.to_dict() for source in self.sources],
            "trace_id": self.trace_id,
        }
