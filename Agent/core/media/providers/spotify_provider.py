from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import requests
from aiohttp import web

from tools.system.pc_control import run_shell_command

from core.media.auth.spotify_oauth import SpotifyOAuthService
from core.media.auth.spotify_token_store import SpotifyTokenStore
from core.media.media_models import MediaCommand, MediaResult, MediaTrack, SpotifyTokenRecord
from core.media.providers.base_provider import BaseMediaProvider

logger = logging.getLogger(__name__)


@dataclass
class _SpotifyPendingAuth:
    user_id: str
    platform: str
    future: asyncio.Future[dict[str, Any]]
    created_at: float


class SpotifyProvider(BaseMediaProvider):
    name = "spotify"

    def __init__(self) -> None:
        raw_base_url = str(os.getenv("SPOTIFY_BASE_URL", "https://api.spotify.com")).strip()
        if not raw_base_url:
            raw_base_url = "https://api.spotify.com"
        if not raw_base_url.startswith("https://"):
            raise ValueError(
                f"SPOTIFY_BASE_URL invalid: {raw_base_url!r}. Must start with 'https://'."
            )
        self._api_base_url = raw_base_url.rstrip("/")
        self.oauth = SpotifyOAuthService()
        self.token_store = SpotifyTokenStore()
        self._auth_lock = asyncio.Lock()
        self._callback_runner: Optional[web.AppRunner] = None
        self._callback_site: Optional[web.BaseSite] = None
        self._callback_path = "/callback"
        self._pending_auth: dict[str, _SpotifyPendingAuth] = {}

    async def can_handle(self, command: MediaCommand, user_id: str) -> bool:
        if not self.oauth.configured or not self.token_store.enabled:
            return False
        token = self.token_store.load_tokens(user_id)
        if not token:
            return False
        text = f"{command.action} {command.query} {command.provider_hint} {command.raw_text}".lower()
        return "spotify" in text or command.action in {
            "play",
            "pause",
            "resume",
            "next",
            "previous",
            "queue",
            "recommend",
            "current",
            "search",
        }

    async def execute(self, command: MediaCommand, user_id: str) -> MediaResult:
        token = await self._get_valid_token(user_id)
        if token is None:
            return MediaResult(
                success=False,
                action=command.action,
                provider=self.name,
                message="Spotify is not connected. Open Settings and connect Spotify.",
            )

        action = command.action
        if action == "pause":
            return await self._simple_player_action(token.access_token, "pause", method="PUT", message="Paused Spotify playback.")
        if action == "resume":
            return await self._simple_player_action(token.access_token, "play", method="PUT", message="Resumed Spotify playback.")
        if action == "next":
            return await self._simple_player_action(token.access_token, "next", method="POST", message="Skipped to next track.")
        if action == "previous":
            return await self._simple_player_action(token.access_token, "previous", method="POST", message="Went to previous track.")
        if action == "current":
            return await self._currently_playing(token.access_token)
        if action == "recommend":
            return await self._recommend(user_id=user_id, access_token=token.access_token)
        if action == "queue":
            return await self._queue(query=command.query, access_token=token.access_token)
        if action in {"play", "search"}:
            return await self._play_or_search(query=command.query or command.raw_text, access_token=token.access_token)

        return MediaResult(success=False, action=action, provider=self.name, message="Unsupported Spotify action.")

    async def _get_valid_token(self, user_id: str) -> Optional[SpotifyTokenRecord]:
        token = self.token_store.load_tokens(user_id)
        if token is None:
            return None
        # expires_at is epoch seconds (wall-clock). Compare with time.time from oauth writes.
        import time as _time

        if token.expires_at <= int(_time.time()) + 60:
            refreshed = await self.oauth.refresh(token.refresh_token)
            if refreshed is None:
                return None
            token = SpotifyTokenRecord(
                user_id=user_id,
                access_token=refreshed.access_token,
                refresh_token=refreshed.refresh_token,
                expires_at=refreshed.expires_at,
                scope=refreshed.scope,
            )
            self.token_store.save_tokens(token)
        return token

    async def prepare_spotify_auth(
        self,
        *,
        user_id: str,
        platform: str = "desktop",
    ) -> dict[str, Any]:
        normalized_platform = "mobile" if str(platform).strip().lower() == "mobile" else "desktop"

        if not self.oauth.client_id:
            return {
                "ok": False,
                "message": "SPOTIFY_CLIENT_ID not set — Spotify OAuth cannot start",
                "code": "spotify_missing_client_id",
            }
        if not self.oauth.client_secret:
            return {
                "ok": False,
                "message": "SPOTIFY_CLIENT_SECRET not set — Spotify OAuth cannot start",
                "code": "spotify_missing_client_secret",
            }
        if not self.token_store.enabled:
            return {
                "ok": False,
                "message": "SPOTIFY_TOKEN_ENC_KEY not set — Spotify OAuth cannot start",
                "code": "spotify_token_store_disabled",
            }

        if normalized_platform == "desktop":
            callback_ready = await self._ensure_callback_server_started()
            if not callback_ready:
                return {
                    "ok": False,
                    "message": "Spotify callback server could not start.",
                    "code": "spotify_callback_unavailable",
                }

        # Keep OAuth state opaque and URL-safe to avoid callback encoding ambiguity.
        state = str(uuid.uuid4())
        auth_url = self.oauth.build_authorize_url(platform=normalized_platform, state=state)
        if not auth_url:
            return {
                "ok": False,
                "message": "Spotify is not configured.",
                "code": "spotify_not_configured",
            }

        loop = asyncio.get_running_loop()
        self._pending_auth[state] = _SpotifyPendingAuth(
            user_id=user_id,
            platform=normalized_platform,
            future=loop.create_future(),
            created_at=time.time(),
        )
        return {
            "ok": True,
            "url": auth_url,
            "state": state,
            "platform": normalized_platform,
        }

    async def wait_for_auth_result(
        self,
        *,
        state: str,
        timeout_s: float = 300.0,
    ) -> dict[str, Any]:
        pending = self._pending_auth.get(state)
        if pending is None:
            return {
                "success": False,
                "message": "Spotify auth session not found.",
                "code": "spotify_invalid_state",
            }

        try:
            result = await asyncio.wait_for(pending.future, timeout=max(1.0, float(timeout_s)))
            if isinstance(result, dict):
                return result
            return {
                "success": False,
                "message": "Spotify authentication failed.",
                "code": "spotify_auth_failed",
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": "Spotify login timed out. Please try again.",
                "code": "spotify_auth_timeout",
            }
        finally:
            self._pending_auth.pop(state, None)

    async def complete_spotify_auth_code(
        self,
        *,
        user_id: str,
        code: str,
        platform: str = "mobile",
    ) -> dict[str, Any]:
        normalized_platform = "mobile" if str(platform).strip().lower() == "mobile" else "desktop"
        auth_code = str(code or "").strip()
        if not auth_code:
            return {
                "success": False,
                "message": "Missing Spotify authorization code.",
                "code": "spotify_missing_code",
            }

        tokens = await self.oauth.exchange_code(auth_code, platform=normalized_platform)
        if tokens is None:
            return {
                "success": False,
                "message": "Spotify authentication failed.",
                "code": "spotify_auth_failed",
            }

        saved = self.token_store.save_tokens(
            SpotifyTokenRecord(
                user_id=user_id,
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                expires_at=tokens.expires_at,
                scope=tokens.scope,
            )
        )
        if not saved:
            return {
                "success": False,
                "message": "Spotify token storage failed.",
                "code": "spotify_token_store_failed",
            }
        return {
            "success": True,
            "connected": True,
            "display_name": user_id.replace("livekit:", "", 1),
        }

    async def _ensure_callback_server_started(self) -> bool:
        if self._callback_site is not None:
            return True

        async with self._auth_lock:
            if self._callback_site is not None:
                return True

            redirect_uri = self.oauth.desktop_redirect_uri
            parsed = urllib.parse.urlparse(redirect_uri)
            host = parsed.hostname or "localhost"
            port = parsed.port or 8888
            self._callback_path = parsed.path or "/callback"

            app = web.Application()
            app.router.add_get(self._callback_path, self._handle_callback_request)
            runner = web.AppRunner(app)
            try:
                await runner.setup()
                site = web.TCPSite(runner, host=host, port=port)
                await site.start()
            except Exception as e:
                logger.error("spotify_callback_server_start_failed error=%s", e, exc_info=True)
                with contextlib.suppress(Exception):
                    await runner.cleanup()
                return False

            self._callback_runner = runner
            self._callback_site = site
            logger.info(
                "spotify_callback_server_ready host=%s port=%s path=%s",
                host,
                port,
                self._callback_path,
            )
        return True

    async def _handle_callback_request(self, request: web.Request) -> web.Response:
        state = str(request.query.get("state") or "").strip()
        code = str(request.query.get("code") or "").strip()
        oauth_error = str(request.query.get("error") or "").strip()

        if not state:
            return self._callback_html(
                "Spotify authentication failed. Missing state. You can close this tab.",
                ok=False,
            )

        if oauth_error:
            self._resolve_pending_auth(
                state,
                {
                    "success": False,
                    "message": f"Spotify authorization was denied ({oauth_error}).",
                    "code": "spotify_auth_denied",
                },
            )
            return self._callback_html(
                "Spotify authorization was denied. You can close this tab.",
                ok=False,
            )

        if not code:
            self._resolve_pending_auth(
                state,
                {
                    "success": False,
                    "message": "Spotify callback missing authorization code.",
                    "code": "spotify_missing_code",
                },
            )
            return self._callback_html(
                "Spotify callback was invalid. You can close this tab.",
                ok=False,
            )

        pending = self._pending_auth.get(state)
        if pending is None:
            return self._callback_html(
                "Spotify login session expired. Please retry from the app.",
                ok=False,
            )

        tokens = await self.oauth.exchange_code(code, platform="desktop")
        if tokens is None:
            self._resolve_pending_auth(
                state,
                {
                    "success": False,
                    "message": "Spotify authentication failed.",
                    "code": "spotify_auth_failed",
                },
            )
            return self._callback_html(
                "Spotify token exchange failed. Please retry.",
                ok=False,
            )

        saved = self.token_store.save_tokens(
            SpotifyTokenRecord(
                user_id=pending.user_id,
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                expires_at=tokens.expires_at,
                scope=tokens.scope,
            )
        )
        if not saved:
            self._resolve_pending_auth(
                state,
                {
                    "success": False,
                    "message": "Spotify token storage failed.",
                    "code": "spotify_token_store_failed",
                },
            )
            return self._callback_html(
                "Spotify token storage failed. Please retry.",
                ok=False,
            )

        self._resolve_pending_auth(
            state,
            {
                "success": True,
                "connected": True,
                "display_name": pending.user_id.replace("livekit:", "", 1),
            },
        )
        return self._callback_html("Spotify connected. You can close this tab.", ok=True)

    def _resolve_pending_auth(self, state: str, payload: dict[str, Any]) -> None:
        pending = self._pending_auth.get(state)
        if pending is None or pending.future.done():
            return
        pending.future.set_result(payload)

    @staticmethod
    def _callback_html(message: str, *, ok: bool) -> web.Response:
        status = "#22c55e" if ok else "#f87171"
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Spotify Auth</title></head>"
            f"<body style=\"font-family:Arial,sans-serif;background:#0b1220;color:#e2e8f0;padding:24px;\">"
            f"<div style=\"max-width:560px;margin:40px auto;border:1px solid {status};padding:20px;"
            "border-radius:12px;\">"
            f"<h2 style=\"margin:0 0 12px;color:{status};\">Spotify</h2>"
            f"<p style=\"margin:0;line-height:1.5;\">{message}</p>"
            "</div></body></html>"
        )
        return web.Response(text=html, content_type="text/html")

    async def _simple_player_action(
        self,
        access_token: str,
        endpoint: str,
        *,
        method: str,
        message: str,
    ) -> MediaResult:
        response = await self._api_request(
            method=method,
            path=f"/me/player/{endpoint}",
            access_token=access_token,
            expected_status={200, 202, 204},
        )
        if response is None:
            return MediaResult(success=False, action=endpoint, provider=self.name, message="I was unable to complete that.")
        return MediaResult(success=True, action=endpoint, provider=self.name, message=message)

    async def _play_or_search(self, query: str, access_token: str) -> MediaResult:
        q = str(query or "").strip()
        if not q:
            return await self._simple_player_action(
                access_token,
                "play",
                method="PUT",
                message="Resumed Spotify playback.",
            )

        track = await self._search_track(access_token, q)
        if track is None:
            spotify_search_url = f"https://open.spotify.com/search/{urllib.parse.quote(q)}"
            await self._open_spotify_url(spotify_search_url)
            return MediaResult(
                success=False,
                action="play",
                provider=self.name,
                message=f"I couldn't find that track directly, so I opened Spotify search for {q}.",
            )

        play_ok = await self._api_request(
            method="PUT",
            path="/me/player/play",
            access_token=access_token,
            json_payload={"uris": [track["uri"]]},
            expected_status={200, 202, 204},
        )
        if play_ok is None:
            await self._open_spotify_url(track["external_url"])
            return MediaResult(
                success=True,
                action="play",
                provider=self.name,
                message=f"Opening {track['title']} on Spotify.",
                track=MediaTrack(
                    title=track["title"],
                    artist=track["artist"],
                    url=track["external_url"],
                    album_art_url=track.get("album_art_url", ""),
                    provider=self.name,
                ),
            )

        return MediaResult(
            success=True,
            action="play",
            provider=self.name,
            message=f"Now playing {track['title']} by {track['artist']} on Spotify.",
            track=MediaTrack(
                title=track["title"],
                artist=track["artist"],
                url=track["external_url"],
                album_art_url=track.get("album_art_url", ""),
                provider=self.name,
            ),
        )

    async def _queue(self, query: str, access_token: str) -> MediaResult:
        track = await self._search_track(access_token, query)
        if track is None:
            return MediaResult(success=False, action="queue", provider=self.name, message="I couldn't find a track to queue.")
        response = await self._api_request(
            method="POST",
            path="/me/player/queue",
            access_token=access_token,
            query_params={"uri": track["uri"]},
            expected_status={200, 202, 204},
        )
        if response is None:
            return MediaResult(success=False, action="queue", provider=self.name, message="I was unable to complete that.")
        return MediaResult(
            success=True,
            action="queue",
            provider=self.name,
            message=f"Added {track['title']} to your Spotify queue.",
            track=MediaTrack(
                title=track["title"],
                artist=track["artist"],
                url=track["external_url"],
                album_art_url=track.get("album_art_url", ""),
                provider=self.name,
            ),
        )

    async def _recommend(self, *, user_id: str, access_token: str) -> MediaResult:  # noqa: ARG002
        current = await self._currently_playing(access_token)
        if not current.success or current.track is None:
            return MediaResult(
                success=False,
                action="recommend",
                provider=self.name,
                message="I couldn't get recommendations right now.",
            )

        search_result = await self._search_track(access_token, f"songs like {current.track.title} {current.track.artist}")
        if search_result is None:
            return MediaResult(
                success=False,
                action="recommend",
                provider=self.name,
                message="I couldn't find recommendations right now.",
            )

        return MediaResult(
            success=True,
            action="recommend",
            provider=self.name,
            message=f"Try {search_result['title']} by {search_result['artist']}.",
            track=MediaTrack(
                title=search_result["title"],
                artist=search_result["artist"],
                url=search_result["external_url"],
                album_art_url=search_result.get("album_art_url", ""),
                provider=self.name,
            ),
        )

    async def _currently_playing(self, access_token: str) -> MediaResult:
        response = await self._api_request(
            method="GET",
            path="/me/player/currently-playing",
            access_token=access_token,
            expected_status={200, 204},
        )
        if response is None:
            return MediaResult(success=False, action="current", provider=self.name, message="Nothing is playing right now.")
        payload = response.json() if response.content else {}
        item = payload.get("item") or {}
        title = str(item.get("name") or "").strip()
        artists = item.get("artists") or []
        artist = str((artists[0] or {}).get("name") or "").strip() if artists else ""
        url = str((item.get("external_urls") or {}).get("spotify") or "").strip()
        album_images = (item.get("album") or {}).get("images") or []
        album_art_url = str((album_images[0] or {}).get("url") or "").strip() if album_images else ""
        if not title:
            return MediaResult(success=False, action="current", provider=self.name, message="Nothing is playing right now.")
        return MediaResult(
            success=True,
            action="current",
            provider=self.name,
            message=f"You're listening to {title} by {artist}." if artist else f"You're listening to {title}.",
            track=MediaTrack(title=title, artist=artist, url=url, album_art_url=album_art_url, provider=self.name),
        )

    async def _search_track(self, access_token: str, query: str) -> Optional[dict[str, str]]:
        response = await self._api_request(
            method="GET",
            path="/search",
            access_token=access_token,
            query_params={"q": query, "type": "track", "limit": 1},
            expected_status={200},
        )
        if response is None:
            return None
        payload = response.json() if response.content else {}
        items = ((payload.get("tracks") or {}).get("items") or [])
        if not items:
            return None
        item = items[0]
        artists = item.get("artists") or []
        album_images = (item.get("album") or {}).get("images") or []
        return {
            "uri": str(item.get("uri") or ""),
            "title": str(item.get("name") or "").strip() or "Unknown track",
            "artist": str((artists[0] or {}).get("name") or "").strip() if artists else "",
            "external_url": str((item.get("external_urls") or {}).get("spotify") or "").strip(),
            "album_art_url": str((album_images[0] or {}).get("url") or "").strip() if album_images else "",
        }

    async def _open_spotify_url(self, url: str) -> None:
        if not url:
            return
        try:
            await run_shell_command(None, f"xdg-open '{url}'")
        except Exception as e:
            logger.warning("spotify_open_url_failed url=%s error=%s", url, e)

    async def _api_request(
        self,
        *,
        method: str,
        path: str,
        access_token: str,
        query_params: Optional[dict[str, Any]] = None,
        json_payload: Optional[dict[str, Any]] = None,
        expected_status: set[int],
        absolute: bool = False,
    ) -> Optional[requests.Response]:
        if absolute:
            url = path
        else:
            normalized_path = path if str(path).startswith("/") else f"/{path}"
            if normalized_path.startswith("/v1/"):
                url = f"{self._api_base_url}{normalized_path}"
            else:
                url = f"{self._api_base_url}/v1{normalized_path}"

        def _request() -> requests.Response:
            return requests.request(
                method=method,
                url=url,
                params=query_params,
                json=json_payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=(3.0, 8.0),
            )

        try:
            response = await asyncio.wait_for(asyncio.to_thread(_request), timeout=10.0)
            if response.status_code in expected_status:
                return response
            logger.warning(
                "spotify_api_request_failed path=%s status=%s body=%s",
                path,
                response.status_code,
                response.text[:180],
            )
            return None
        except Exception as e:
            logger.warning("spotify_api_request_exception path=%s error=%s", path, e)
            return None
