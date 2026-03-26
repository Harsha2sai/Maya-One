from __future__ import annotations

import os
import re

from core.research.base_provider import BaseSearchProvider
from core.research.research_models import SourceItem


class FinanceProvider(BaseSearchProvider):
    name = "finance"
    api_key_env = "ALPHA_VANTAGE_API_KEY"

    async def _search_impl(
        self,
        *,
        query: str,
        max_results: int,
        timeout_s: float,
    ) -> list[SourceItem]:
        api_key = os.getenv(self.api_key_env, "").strip()
        symbol = self._extract_symbol(query)
        if not symbol:
            return []

        data = await self._get_json(
            "https://www.alphavantage.co/query",
            params={
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": api_key,
            },
            timeout_s=timeout_s,
        )
        quote = data.get("Global Quote") or {}
        price = quote.get("05. price")
        change = quote.get("10. change percent")
        if not price:
            return []

        snippet = f"{symbol} currently trades at {price} USD ({change})."
        return [
            self._item(
                title=f"{symbol} stock price",
                url=f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}",
                snippet=snippet,
            )
        ]

    @staticmethod
    def _extract_symbol(query: str) -> str:
        upper = str(query or "").upper()
        ticker_match = re.search(r"\b[A-Z]{1,5}\b", upper)
        if ticker_match:
            token = ticker_match.group(0)
            if token not in {"NEWS", "PRICE", "STOCK", "LATEST", "ABOUT"}:
                return token
        common = {
            "TESLA": "TSLA",
            "APPLE": "AAPL",
            "MICROSOFT": "MSFT",
            "GOOGLE": "GOOGL",
            "AMAZON": "AMZN",
            "NVIDIA": "NVDA",
        }
        for key, value in common.items():
            if key in upper:
                return value
        return ""
