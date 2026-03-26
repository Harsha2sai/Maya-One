import pytest

from core.media.auth.spotify_oauth import SpotifyOAuthService


def test_build_authorize_url_includes_redirect(monkeypatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI_DESKTOP", "http://localhost:8888/callback")

    oauth = SpotifyOAuthService()
    url = oauth.build_authorize_url(platform="desktop", state="abc")

    assert url is not None
    assert "accounts.spotify.com/authorize" in url
    assert "client_id=cid" in url
    assert "state=abc" in url


@pytest.mark.asyncio
async def test_exchange_code_returns_none_when_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)

    oauth = SpotifyOAuthService()
    tokens = await oauth.exchange_code("code")
    assert tokens is None
