from __future__ import annotations

import asyncio
import logging
import os
import urllib.parse

import requests

from tools.system.pc_control import run_shell_command

from core.media.media_models import MediaCommand, MediaResult, MediaTrack
from core.media.providers.base_provider import BaseMediaProvider

logger = logging.getLogger(__name__)


class YouTubeProvider(BaseMediaProvider):
    name = "youtube"

    def __init__(self) -> None:
        self.api_key = str(os.getenv("YOUTUBE_API_KEY", "")).strip()

    async def can_handle(self, command: MediaCommand, user_id: str) -> bool:  # noqa: ARG002
        text = f"{command.action} {command.query} {command.provider_hint}".lower()
        return "youtube" in text or "video" in text

    async def execute(self, command: MediaCommand, user_id: str) -> MediaResult:  # noqa: ARG002
        query = (command.query or command.raw_text or "").strip()
        if not query:
            return await self._open_url("https://youtube.com", command.action, message="Opening YouTube.")

        if not self.api_key:
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
            return await self._open_url(search_url, command.action, message=f"Opening YouTube search for {query}.")

        search_result = await self._search(query)
        if search_result is None:
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
            return await self._open_url(search_url, command.action, message=f"Opening YouTube search for {query}.")

        video_id = search_result.get("videoId", "")
        title = search_result.get("title", "YouTube result")
        url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        if not url:
            return MediaResult(success=False, action=command.action, provider=self.name, message="No video found.")

        opened = await self._open_url(url, command.action, message=f"Playing {title} on YouTube.")
        opened.track = MediaTrack(title=title, artist="", url=url, provider=self.name)
        return opened

    async def _search(self, query: str) -> dict | None:
        params = {
            "part": "snippet",
            "q": query,
            "maxResults": 1,
            "type": "video",
            "key": self.api_key,
        }

        def _request() -> requests.Response:
            return requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params,
                timeout=(3.0, 8.0),
            )

        try:
            response = await asyncio.wait_for(asyncio.to_thread(_request), timeout=10.0)
            if response.status_code >= 400:
                logger.warning("youtube_search_failed status=%s", response.status_code)
                return None
            payload = response.json()
            items = payload.get("items") or []
            if not items:
                return None
            first = items[0]
            return {
                "videoId": str((first.get("id") or {}).get("videoId") or "").strip(),
                "title": str((first.get("snippet") or {}).get("title") or "").strip(),
            }
        except Exception as e:
            logger.warning("youtube_search_exception query=%s error=%s", query, e)
            return None

    async def _open_url(self, url: str, action: str, message: str) -> MediaResult:
        try:
            await run_shell_command(None, f"xdg-open '{url}'")
            return MediaResult(success=True, action=action, provider=self.name, message=message)
        except Exception as e:
            logger.warning("youtube_open_failed url=%s error=%s", url, e)
            return MediaResult(success=False, action=action, provider=self.name, message="I was unable to complete that.")
