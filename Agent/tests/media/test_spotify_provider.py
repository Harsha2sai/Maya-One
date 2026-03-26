from unittest.mock import AsyncMock, MagicMock

import pytest

from core.media.media_models import MediaCommand, SpotifyTokenRecord
from core.media.providers.spotify_provider import SpotifyProvider


@pytest.mark.asyncio
async def test_spotify_provider_requires_connection(monkeypatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIFY_TOKEN_ENC_KEY", "enc-key")

    provider = SpotifyProvider()
    provider.token_store = MagicMock()
    provider.token_store.enabled = True
    provider.token_store.load_tokens.return_value = None

    result = await provider.execute(MediaCommand(action="play", query="song"), user_id="u1")
    assert result.success is False
    assert "not connected" in result.message.lower()


@pytest.mark.asyncio
async def test_spotify_provider_pause_uses_player_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIFY_TOKEN_ENC_KEY", "enc-key")

    provider = SpotifyProvider()
    provider.token_store = MagicMock()
    provider.token_store.enabled = True
    provider.token_store.load_tokens.return_value = SpotifyTokenRecord(
        user_id="u1",
        access_token="token",
        refresh_token="refresh",
        expires_at=9999999999,
        scope="",
    )
    provider._api_request = AsyncMock(return_value=object())

    result = await provider.execute(MediaCommand(action="pause"), user_id="u1")
    assert result.success is True
    assert "paused" in result.message.lower()


@pytest.mark.asyncio
async def test_prepare_spotify_auth_requires_client_id(monkeypatch) -> None:
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIFY_TOKEN_ENC_KEY", "enc-key")

    provider = SpotifyProvider()
    result = await provider.prepare_spotify_auth(user_id="livekit:u1", platform="desktop")

    assert result["ok"] is False
    assert result["code"] == "spotify_missing_client_id"
    assert "SPOTIFY_CLIENT_ID not set" in result["message"]


@pytest.mark.asyncio
async def test_wait_for_auth_result_returns_invalid_state_when_unknown(monkeypatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIFY_TOKEN_ENC_KEY", "enc-key")

    provider = SpotifyProvider()
    result = await provider.wait_for_auth_result(state="missing-state", timeout_s=1.0)

    assert result["success"] is False
    assert result["code"] == "spotify_invalid_state"


@pytest.mark.asyncio
async def test_complete_spotify_auth_code_saves_tokens(monkeypatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIFY_TOKEN_ENC_KEY", "enc-key")

    provider = SpotifyProvider()
    provider.oauth = MagicMock()
    provider.oauth.exchange_code = AsyncMock(
        return_value=MagicMock(
            access_token="a",
            refresh_token="r",
            expires_at=12345,
            scope="scope",
        )
    )
    provider.token_store = MagicMock()
    provider.token_store.save_tokens.return_value = True

    result = await provider.complete_spotify_auth_code(
        user_id="livekit:u1",
        code="code-1",
        platform="mobile",
    )

    assert result["success"] is True
    provider.oauth.exchange_code.assert_awaited_once()
    provider.token_store.save_tokens.assert_called_once()


@pytest.mark.asyncio
async def test_search_track_uses_v1_path_without_absolute_mode(monkeypatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIFY_TOKEN_ENC_KEY", "enc-key")

    provider = SpotifyProvider()
    provider._api_request = AsyncMock(return_value=None)

    await provider._search_track(access_token="token", query="lofi")

    provider._api_request.assert_awaited_once()
    kwargs = provider._api_request.await_args.kwargs
    assert kwargs["path"] == "/search"
    assert "absolute" not in kwargs


def test_spotify_provider_validates_base_url(monkeypatch) -> None:
    monkeypatch.setenv("SPOTIFY_BASE_URL", "http://api.spotify.com")
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIFY_TOKEN_ENC_KEY", "enc-key")

    with pytest.raises(ValueError, match="SPOTIFY_BASE_URL invalid"):
        SpotifyProvider()
