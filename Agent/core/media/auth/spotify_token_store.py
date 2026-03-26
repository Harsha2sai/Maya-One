from __future__ import annotations

import base64
import hashlib
import logging
import os
import sqlite3
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from core.media.media_models import SpotifyTokenRecord

logger = logging.getLogger(__name__)


class SpotifyTokenStore:
    def __init__(self) -> None:
        self.db_path = os.getenv("DATABASE_URL", "sqlite:///./dev_maya_one.db").replace("sqlite:///", "")
        self._fernet = self._build_fernet()
        self._create_table()

    @staticmethod
    def _build_fernet() -> Optional[Fernet]:
        secret = str(os.getenv("SPOTIFY_TOKEN_ENC_KEY", "")).strip()
        if not secret:
            return None
        try:
            # Accept raw text or already-base64 Fernet key.
            if len(secret) == 44 and secret.endswith("="):
                return Fernet(secret.encode("utf-8"))
            digest = hashlib.sha256(secret.encode("utf-8")).digest()
            return Fernet(base64.urlsafe_b64encode(digest))
        except Exception as e:
            logger.warning("spotify_token_store_encryption_key_invalid error=%s", e)
            return None

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def _create_table(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS spotify_tokens (
                    user_id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    scope TEXT DEFAULT ''
                )
                """
            )

    def _encrypt(self, value: str) -> str:
        if not self._fernet:
            raise RuntimeError("spotify_token_store_disabled")
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def _decrypt(self, value: str) -> str:
        if not self._fernet:
            raise RuntimeError("spotify_token_store_disabled")
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")

    def save_tokens(self, record: SpotifyTokenRecord) -> bool:
        if not self.enabled:
            logger.warning("spotify_not_configured reason=missing_token_encryption_key")
            return False
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO spotify_tokens(user_id, access_token, refresh_token, expires_at, scope)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        access_token=excluded.access_token,
                        refresh_token=excluded.refresh_token,
                        expires_at=excluded.expires_at,
                        scope=excluded.scope
                    """,
                    (
                        record.user_id,
                        self._encrypt(record.access_token),
                        self._encrypt(record.refresh_token),
                        int(record.expires_at),
                        record.scope,
                    ),
                )
            return True
        except Exception as e:
            logger.error("spotify_token_store_save_failed error=%s", e, exc_info=True)
            return False

    def load_tokens(self, user_id: str) -> Optional[SpotifyTokenRecord]:
        if not self.enabled:
            return None
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT user_id, access_token, refresh_token, expires_at, scope FROM spotify_tokens WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
            if not row:
                return None
            access_token = self._decrypt(str(row[1]))
            refresh_token = self._decrypt(str(row[2]))
            return SpotifyTokenRecord(
                user_id=str(row[0]),
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=int(row[3]),
                scope=str(row[4] or ""),
            )
        except (InvalidToken, RuntimeError) as e:
            logger.warning("spotify_token_store_load_failed user_id=%s error=%s", user_id, e)
            return None
        except Exception as e:
            logger.error("spotify_token_store_load_unexpected user_id=%s error=%s", user_id, e, exc_info=True)
            return None

    def delete_tokens(self, user_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM spotify_tokens WHERE user_id = ?", (user_id,))
            return True
        except Exception as e:
            logger.error("spotify_token_store_delete_failed user_id=%s error=%s", user_id, e)
            return False
