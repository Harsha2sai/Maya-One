"""SessionStore for filesystem-backed memdir session persistence."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SessionStore:
    """Persist session snapshots as JSON with atomic writes."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        root = Path(base_dir).expanduser().resolve() if base_dir else self._default_root()
        self._sessions_dir = root / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def save(self, session_id: str, payload: Dict[str, Any]) -> Path:
        normalized_id = self._normalize_id(session_id)
        record = {
            "session_id": normalized_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "data": dict(payload or {}),
        }
        target = self._path_for(normalized_id)
        self._atomic_write_json(target, record)
        return target

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        normalized_id = self._normalize_id(session_id)
        path = self._path_for(normalized_id)
        if not path.exists():
            return None
        return self._read_json(path)

    def list_sessions(self) -> List[str]:
        session_ids: List[str] = []
        for file_path in sorted(self._sessions_dir.glob("*.json")):
            session_ids.append(file_path.stem)
        return session_ids

    def delete(self, session_id: str) -> bool:
        normalized_id = self._normalize_id(session_id)
        path = self._path_for(normalized_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    @staticmethod
    def _default_root() -> Path:
        return Path(os.path.expanduser("~/.maya/memdir")).resolve()

    def _path_for(self, session_id: str) -> Path:
        return self._sessions_dir / f"{session_id}.json"

    @staticmethod
    def _normalize_id(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("session_id is required")
        return normalized

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {"data": payload}

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
