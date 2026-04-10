"""Agent context snapshots for memdir runtime recovery and continuity."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class AgentContextStore:
    """Persist/retrieve per-agent context payloads as JSON."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        root = Path(base_dir).expanduser().resolve() if base_dir else self._default_root()
        self._contexts_dir = root / "contexts"
        self._contexts_dir.mkdir(parents=True, exist_ok=True)

    def save_context(self, agent_id: str, context: Dict[str, Any]) -> Path:
        normalized_agent = self._normalize_agent(agent_id)
        payload = {
            "agent_id": normalized_agent,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "context": dict(context or {}),
        }
        path = self._path_for(normalized_agent)
        self._atomic_write_json(path, payload)
        return path

    def load_context(self, agent_id: str) -> Optional[Dict[str, Any]]:
        normalized_agent = self._normalize_agent(agent_id)
        path = self._path_for(normalized_agent)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return None
        return payload

    def clear_context(self, agent_id: str) -> bool:
        normalized_agent = self._normalize_agent(agent_id)
        path = self._path_for(normalized_agent)
        if not path.exists():
            return False
        path.unlink()
        return True

    @staticmethod
    def _default_root() -> Path:
        return Path(os.path.expanduser("~/.maya/memdir")).resolve()

    def _path_for(self, agent_id: str) -> Path:
        return self._contexts_dir / f"{agent_id}.json"

    @staticmethod
    def _normalize_agent(agent_id: str) -> str:
        normalized = str(agent_id or "").strip()
        if not normalized:
            raise ValueError("agent_id is required")
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
