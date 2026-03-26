from __future__ import annotations

import re

from .research_models import ProviderTask

ALWAYS_SEARCH_PATTERNS = (
    r"\bwho is (?:the )?(?:ceo|cto|cfo|president|founder|head)\s+of\b",
    r"\bwho (?:runs|leads|owns|heads)\b",
    r"\bcurrent (?:ceo|cto|leader|head|president)\b",
    r"\bwho is in charge of\b",
    r"\blatest news\b",
    r"\bwhat (?:happened|is happening)\b",
    r"\brecent(?:ly)?\b",
    r"\bright now\b",
    r"\btoday\b",
    r"\bthis week\b",
)


def build_research_tasks(query: str) -> tuple[list[ProviderTask], str]:
    q = str(query or "").strip()
    if not q:
        return [], ""

    ql = q.lower()
    tasks: list[ProviderTask] = []

    if any(token in ql for token in ["weather", "temperature", "rain", "forecast"]):
        tasks.append(ProviderTask(provider="weather", query=q, max_results=1))
        tasks.append(
            ProviderTask(provider="tavily", query=f"{q} latest forecast details", max_results=2)
        )
        return tasks, q

    if any(token in ql for token in ["stock", "share", "price", "market", "nasdaq", "dow"]):
        tasks.append(ProviderTask(provider="finance", query=q, max_results=1))
        tasks.append(ProviderTask(provider="news", query=q, max_results=3))
        tasks.append(ProviderTask(provider="tavily", query=f"{q} analysis", max_results=2))
        return tasks, q

    if any(re.search(pattern, ql) for pattern in ALWAYS_SEARCH_PATTERNS):
        tasks.append(ProviderTask(provider="news", query=q, max_results=4))
        tasks.append(ProviderTask(provider="tavily", query=q, max_results=4))
        tasks.append(ProviderTask(provider="serper", query=q, max_results=3))
        return tasks, q

    if any(token in ql for token in ["news", "latest", "happening", "headline"]):
        tasks.append(ProviderTask(provider="news", query=q, max_results=4))
        tasks.append(ProviderTask(provider="tavily", query=q, max_results=3))
        return tasks, q

    if re.search(r"\b(my location|where am i)\b", ql):
        tasks.append(ProviderTask(provider="geo", query=q, max_results=1))
        return tasks, q

    if any(token in ql for token in ["who is", "what is", "tell me about", "history"]):
        tasks.append(ProviderTask(provider="wikipedia", query=q, max_results=3))
        tasks.append(ProviderTask(provider="tavily", query=q, max_results=3))
        return tasks, q

    return [
        ProviderTask(provider="tavily", query=q, max_results=4),
        ProviderTask(provider="wikipedia", query=q, max_results=2),
    ], q
