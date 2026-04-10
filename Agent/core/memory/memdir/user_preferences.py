"""User preferences store for memdir JSON key-value persistence."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class UserPreferences:
    """Manage per-user preference maps on disk."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        root = Path(base_dir).expanduser().resolve() if base_dir else self._default_root()
        self._prefs_dir = root / "prefs"
        self._prefs_dir.mkdir(parents=True, exist_ok=True)

    def set(self, user_id: str, key: str, value: Any) -> None:
        normalized_user = self._normalize_user(user_id)
        normalized_key = self._normalize_key(key)

        payload = self._load_raw(normalized_user)
        values = dict(payload.get("values") or {})
        values[normalized_key] = value

        updated = {
            "user_id": normalized_user,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "values": values,
        }
        self._atomic_write_json(self._path_for(normalized_user), updated)

    def get(self, user_id: str, key: str, default: Any = None) -> Any:
        normalized_user = self._normalize_user(user_id)
        normalized_key = self._normalize_key(key)

        payload = self._load_raw(normalized_user)
        values = dict(payload.get("values") or {})
        return values.get(normalized_key, default)

    def get_all(self, user_id: str) -> Dict[str, Any]:
        normalized_user = self._normalize_user(user_id)
        payload = self._load_raw(normalized_user)
        return dict(payload.get("values") or {})

    def delete(self, user_id: str, key: Optional[str] = None) -> bool:
        normalized_user = self._normalize_user(user_id)
        path = self._path_for(normalized_user)
        if not path.exists():
            return False

        if key is None:
            path.unlink()
            return True

        normalized_key = self._normalize_key(key)
        payload = self._load_raw(normalized_user)
        values = dict(payload.get("values") or {})
        if normalized_key not in values:
            return False

        del values[normalized_key]
        updated = {
            "user_id": normalized_user,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "values": values,
        }
        self._atomic_write_json(path, updated)
        return True

    @staticmethod
    def _default_root() -> Path:
        return Path(os.path.expanduser("~/.maya/memdir")).resolve()

    def _path_for(self, user_id: str) -> Path:
        return self._prefs_dir / f"{user_id}.json"

    def _load_raw(self, user_id: str) -> Dict[str, Any]:
        path = self._path_for(user_id)
        if not path.exists():
            return {"user_id": user_id, "values": {}}
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return {"user_id": user_id, "values": {}}
        return payload

    @staticmethod
    def _normalize_user(user_id: str) -> str:
        normalized = str(user_id or "").strip()
        if not normalized:
            raise ValueError("user_id is required")
        return normalized

    @staticmethod
    def _normalize_key(key: str) -> str:
        normalized = str(key or "").strip()
        if not normalized:
            raise ValueError("key is required")
        return normalized

    @staticmethod
    def _atomic_write_json(target: Path, payload: Dict[str, Any]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, target)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
