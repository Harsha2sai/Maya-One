import os

from core.media.auth.spotify_token_store import SpotifyTokenStore
from core.media.media_models import SpotifyTokenRecord


def test_spotify_token_store_save_and_load(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "tokens.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SPOTIFY_TOKEN_ENC_KEY", "unit-test-secret-key")

    store = SpotifyTokenStore()
    record = SpotifyTokenRecord(
        user_id="u1",
        access_token="access",
        refresh_token="refresh",
        expires_at=123456,
        scope="scope",
    )

    assert store.save_tokens(record) is True
    loaded = store.load_tokens("u1")
    assert loaded is not None
    assert loaded.access_token == "access"
    assert loaded.refresh_token == "refresh"


def test_spotify_token_store_disabled_without_key(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "tokens_disabled.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.delenv("SPOTIFY_TOKEN_ENC_KEY", raising=False)

    store = SpotifyTokenStore()
    assert store.enabled is False
