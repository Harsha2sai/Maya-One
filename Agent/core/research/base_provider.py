from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

import aiohttp

from .research_models import SourceItem

logger = logging.getLogger(__name__)


class BaseSearchProvider(ABC):
    name: str = "base"
    api_key_env: Optional[str] = None

    def is_configured(self) -> bool:
        if not self.api_key_env:
            return True
        return bool(str(os.getenv(self.api_key_env, "")).strip())

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        timeout_s: float = 8.0,
    ) -> list[SourceItem]:
        if not self.is_configured():
            logger.warning(
                "research_provider_skipped provider=%s reason=missing_api_key env=%s",
                self.name,
                self.api_key_env,
            )
            return []
        try:
            return await asyncio.wait_for(
                self._search_impl(query=query, max_results=max_results, timeout_s=timeout_s),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning("research_provider_timeout provider=%s query=%s", self.name, query)
            return []
        except Exception as e:
            logger.warning(
                "research_provider_failed provider=%s query=%s error=%s",
                self.name,
                query,
                e,
            )
            return []

    @abstractmethod
    async def _search_impl(
        self,
        *,
        query: str,
        max_results: int,
        timeout_s: float,
    ) -> list[SourceItem]:
        raise NotImplementedError

    async def _get_json(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        timeout_s: float = 8.0,
    ) -> Any:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status >= 400:
                    text = await response.text()
                    raise RuntimeError(f"http_{response.status}:{text[:180]}")
                return await response.json(content_type=None)

    def _item(self, *, title: str, url: str, snippet: str) -> SourceItem:
        return SourceItem.from_values(
            title=title,
            url=url,
            snippet=snippet,
            provider=self.name,
        )
