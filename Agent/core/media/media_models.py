from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse


@dataclass
class MediaTrack:
    title: str
    artist: str = ""
    url: str = ""
    album_art_url: str = ""
    provider: str = "unknown"

    @property
    def domain(self) -> str:
        parsed = urlparse(self.url.strip())
        return (parsed.netloc or "").replace("www.", "")


@dataclass
class MediaResult:
    success: bool
    action: str
    provider: str
    message: str
    track: Optional[MediaTrack] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "provider": self.provider,
            "track_name": self.track.title if self.track else None,
            "artist": self.track.artist if self.track else None,
            "album_art_url": self.track.album_art_url if self.track else None,
            "track_url": self.track.url if self.track else None,
        }


@dataclass
class MediaCommand:
    action: str
    query: str = ""
    provider_hint: str = ""
    raw_text: str = ""


@dataclass
class SpotifyTokenRecord:
    user_id: str
    access_token: str
    refresh_token: str
    expires_at: int
    scope: str
