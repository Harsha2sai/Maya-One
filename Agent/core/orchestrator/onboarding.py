"""
First-run onboarding flow for new users.

Detects when a user has no preferences and injects a structured
onboarding prompt into the first chat turn. Captures preferences
from the user's natural response and persists them.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Onboarding is complete when these keys are present
ONBOARDING_KEYS = ("music_app", "home_city")

ONBOARDING_PROMPT = (
    "Hi! Before we get started, I'd love to personalise your experience. "
    "Which music app do you use — Spotify, YouTube Music, or something else? "
    "And what city are you based in?"
)

# Extraction patterns for onboarding response
_MUSIC_APP_PATTERNS = [
    (r"\bspotify\b", "spotify"),
    (r"\byoutube\s*music\b", "youtube music"),
    (r"\byoutube\b", "youtube"),
    (r"\bvlc\b", "vlc"),
    (r"\bapple\s*music\b", "apple music"),
]

_CITY_PATTERN = re.compile(
    r"\b(?:i(?:'m| am)\s+(?:from|in|based in)|from|in)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b"
)


def is_onboarding_complete(prefs: dict) -> bool:
    """Return True if all required onboarding keys are present and non-empty."""
    return all(prefs.get(k) for k in ONBOARDING_KEYS)


def extract_onboarding_prefs(text: str) -> dict[str, str]:
    """Extract music_app and home_city from a natural language response."""
    extracted: dict[str, str] = {}
    lower = text.lower()

    for pattern, value in _MUSIC_APP_PATTERNS:
        if re.search(pattern, lower):
            extracted["music_app"] = value
            break

    city_match = _CITY_PATTERN.search(text)
    if city_match:
        extracted["home_city"] = city_match.group(1).strip()

    return extracted


def build_onboarding_system_note() -> str:
    """Return a system note to inject when onboarding is needed."""
    return (
        "[ONBOARDING] This is a new user with no preferences set. "
        "Ask them which music app they use and what city they are based in. "
        "Keep it warm and brief. After they answer, confirm what you captured."
    )
