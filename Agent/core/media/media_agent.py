from __future__ import annotations

import logging
import time
from typing import Optional

from tools.system.pc_control import run_shell_command

from core.media.auth.spotify_oauth import SpotifyOAuthService
from core.media.auth.spotify_token_store import SpotifyTokenStore
from core.media.media_models import MediaResult, SpotifyTokenRecord
from core.media.media_router import MediaRouter
from core.media.providers import PlayerctlProvider, SpotifyProvider, YouTubeProvider

logger = logging.getLogger(__name__)


class MediaAgent:
    def __init__(self) -> None:
        self.router = MediaRouter()
        self.spotify = SpotifyProvider()
        self.youtube = YouTubeProvider()
        self.playerctl = PlayerctlProvider()
        self.spotify_oauth = SpotifyOAuthService()
        self.spotify_token_store = SpotifyTokenStore()

    async def run(
        self,
        *,
        command: str,
        user_id: str,
        session_id: str,
        trace_id: str,
    ) -> MediaResult:
        started = time.monotonic()
        parsed = self.router.parse(command)
        provider_hint = self.router.choose_provider(parsed)

        provider_result: Optional[MediaResult] = None
        if provider_hint == "youtube":
            provider_result = await self.youtube.execute(parsed, user_id)
        else:
            if await self.spotify.can_handle(parsed, user_id):
                provider_result = await self.spotify.execute(parsed, user_id)
            if provider_result is None or not provider_result.success:
                if await self.youtube.can_handle(parsed, user_id):
                    provider_result = await self.youtube.execute(parsed, user_id)
            if provider_result is None or not provider_result.success:
                provider_result = await self.playerctl.execute(parsed, user_id)
            if (
                (provider_result is None or not provider_result.success)
                and parsed.action in {"play", "search", "recommend", "queue"}
            ):
                provider_result = await self._open_music_player_fallback(parsed.query or parsed.raw_text, parsed.action)

        if provider_result is None:
            provider_result = MediaResult(
                success=False,
                action=parsed.action,
                provider="unknown",
                message="I was unable to complete that.",
            )

        duration_ms = int(max(0.0, (time.monotonic() - started) * 1000.0))
        provider_result.metadata["duration_ms"] = duration_ms
        provider_result.metadata["trace_id"] = trace_id

        logger.info(
            "media_route_completed action=%s provider=%s success=%s duration_ms=%s session_id=%s trace_id=%s",
            provider_result.action,
            provider_result.provider,
            provider_result.success,
            duration_ms,
            session_id,
            trace_id,
        )
        return provider_result

    async def _open_music_player_fallback(self, request: str, action: str) -> MediaResult:
        query = str(request or "").strip()
        target = "https://open.spotify.com"
        if query:
            message = f"Opening music player for {query}."
        else:
            message = "Opening your music player."
        try:
            await run_shell_command(None, f"xdg-open '{target}'")
            return MediaResult(
                success=True,
                action=action or "play",
                provider="fallback",
                message=message,
            )
        except Exception as e:
            logger.warning("media_open_player_fallback_failed query=%s error=%s", query, e)
            return MediaResult(
                success=False,
                action=action or "play",
                provider="fallback",
                message="I was unable to complete that.",
            )

    def get_spotify_auth_url(self, platform: str = "desktop", state: str = "maya") -> Optional[str]:
        return self.spotify_oauth.build_authorize_url(platform=platform, state=state)

    async def complete_spotify_auth(self, *, user_id: str, code: str, platform: str = "desktop") -> bool:
        tokens = await self.spotify_oauth.exchange_code(code, platform=platform)
        if tokens is None:
            return False
        return self.spotify_token_store.save_tokens(
            SpotifyTokenRecord(
                user_id=user_id,
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                expires_at=tokens.expires_at,
                scope=tokens.scope,
            )
        )

    def is_spotify_connected(self, user_id: str) -> bool:
        return self.spotify_token_store.load_tokens(user_id) is not None

    def disconnect_spotify(self, user_id: str) -> bool:
        return self.spotify_token_store.delete_tokens(user_id)
