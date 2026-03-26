from __future__ import annotations

import asyncio
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
_SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


@dataclass
class SpotifyOAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: int
    scope: str


class SpotifyOAuthService:
    def __init__(self) -> None:
        self.client_id = str(os.getenv("SPOTIFY_CLIENT_ID", "")).strip()
        self.client_secret = str(os.getenv("SPOTIFY_CLIENT_SECRET", "")).strip()
        self.desktop_redirect_uri = str(
            os.getenv("SPOTIFY_REDIRECT_URI_DESKTOP", "http://localhost:8888/callback")
        ).strip()
        self.mobile_redirect_uri = str(
            os.getenv("SPOTIFY_REDIRECT_URI_MOBILE", "maya://spotify/callback")
        ).strip()
        self.scope = str(
            os.getenv(
                "SPOTIFY_SCOPES",
                "user-read-playback-state user-modify-playback-state user-library-modify "
                "playlist-read-private streaming user-read-currently-playing",
            )
        ).strip()

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def build_authorize_url(self, platform: str = "desktop", state: str = "maya") -> Optional[str]:
        if not self.configured:
            return None
        redirect_uri = self.mobile_redirect_uri if platform == "mobile" else self.desktop_redirect_uri
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": self.scope,
            "state": state,
            "show_dialog": "true",
        }
        return f"{_SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, platform: str = "desktop") -> Optional[SpotifyOAuthTokens]:
        redirect_uri = self.mobile_redirect_uri if platform == "mobile" else self.desktop_redirect_uri
        return await self._request_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            }
        )

    async def refresh(self, refresh_token: str) -> Optional[SpotifyOAuthTokens]:
        return await self._request_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )

    async def _request_token(self, form_data: dict[str, Any]) -> Optional[SpotifyOAuthTokens]:
        if not self.configured:
            logger.warning("spotify_not_configured reason=missing_client_credentials")
            return None

        def _post() -> requests.Response:
            return requests.post(
                _SPOTIFY_TOKEN_URL,
                data=form_data,
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=(3.0, 8.0),
            )

        try:
            response = await asyncio.wait_for(asyncio.to_thread(_post), timeout=10.0)
            if response.status_code >= 400:
                logger.warning(
                    "spotify_token_request_failed status=%s body=%s",
                    response.status_code,
                    response.text[:200],
                )
                return None
            payload = response.json() if response.content else {}
            access_token = str(payload.get("access_token") or "").strip()
            refresh_token = str(payload.get("refresh_token") or form_data.get("refresh_token") or "").strip()
            expires_in = int(payload.get("expires_in") or 3600)
            if not access_token or not refresh_token:
                return None
            return SpotifyOAuthTokens(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=int(time.time()) + max(60, expires_in),
                scope=str(payload.get("scope") or self.scope),
            )
        except Exception as e:
            logger.warning("spotify_token_request_exception error=%s", e)
            return None
