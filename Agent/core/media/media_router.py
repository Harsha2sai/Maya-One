from __future__ import annotations

import re
from dataclasses import dataclass

from core.media.media_models import MediaCommand


@dataclass
class MediaRouteDecision:
    provider_hint: str
    command: MediaCommand


class MediaRouter:
    _YOUTUBE_PATTERNS = (
        r"\byoutube\b",
        r"\bvideo\b",
        r"\bwatch\b",
    )

    def parse(self, text: str) -> MediaCommand:
        raw = str(text or "").strip()
        normalized = re.sub(r"\s+", " ", raw.lower()).strip()
        play_intent_patterns = (
            r"\bstart\s+playing\b",
            r"\bput\s+on\b",
            r"\bplay\s+something\b",
            r"\bi want to listen\b",
            r"\bsomething\s+relaxing\b",
            r"\bplay\s+some\s+\w+",
        )

        if re.search(r"\b(next|skip)\b", normalized):
            return MediaCommand(action="next", raw_text=raw)
        if re.search(r"\b(previous|prev|back)\b", normalized):
            return MediaCommand(action="previous", raw_text=raw)
        if re.search(r"\bpause\b", normalized):
            return MediaCommand(action="pause", raw_text=raw)
        if re.search(r"\b(resume|continue)\b", normalized):
            return MediaCommand(action="resume", raw_text=raw)
        if re.search(r"\b(stop)\b", normalized):
            return MediaCommand(action="stop", raw_text=raw)
        if re.search(r"\b(queue|add to queue)\b", normalized):
            query = self._extract_query(normalized)
            return MediaCommand(action="queue", query=query, raw_text=raw)
        if re.search(r"\b(recommend|suggest|discover)\b", normalized):
            return MediaCommand(action="recommend", raw_text=raw)
        if re.search(r"\b(current|what.?s playing|now playing)\b", normalized):
            return MediaCommand(action="current", raw_text=raw)
        if re.search(r"\b(search)\b", normalized):
            query = self._extract_query(normalized)
            return MediaCommand(action="search", query=query, raw_text=raw)
        if any(re.search(pattern, normalized) for pattern in play_intent_patterns):
            query = self._extract_query(normalized)
            return MediaCommand(action="play", query=query or normalized, raw_text=raw)
        if re.search(r"\b(play)\b", normalized):
            query = self._extract_query(normalized)
            return MediaCommand(action="play", query=query, raw_text=raw)

        return MediaCommand(action="search", query=raw, raw_text=raw)

    def choose_provider(self, command: MediaCommand) -> str:
        text = f"{command.raw_text} {command.query}".lower()
        if any(re.search(pattern, text) for pattern in self._YOUTUBE_PATTERNS):
            return "youtube"
        return "spotify"

    @staticmethod
    def _extract_query(text: str) -> str:
        candidate = re.sub(r"^(play|search|watch|open)\s+", "", text, flags=re.IGNORECASE)
        candidate = re.sub(r"\bon\s+youtube\b", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\bon\s+spotify\b", "", candidate, flags=re.IGNORECASE)
        return candidate.strip()
