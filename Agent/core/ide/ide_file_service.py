from __future__ import annotations

from pathlib import Path
from typing import Any

from .ide_session_manager import IDESessionManager, SessionNotFoundError


class PathEscapeError(ValueError):
    """Raised when a relative path escapes the workspace root."""


class IDEFileService:
    def __init__(self, session_manager: IDESessionManager) -> None:
        self._session_manager = session_manager

    def _require_workspace(self, session_id: str) -> Path:
        session = self._session_manager.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return Path(session.workspace_path).resolve()

    def _resolve_path(self, workspace_root: Path, relative_path: str) -> Path:
        rel = (relative_path or "").strip()
        candidate = (workspace_root / rel).resolve()
        if candidate == workspace_root:
            return candidate
        if workspace_root not in candidate.parents:
            raise PathEscapeError(f"Path escapes workspace: {relative_path}")
        return candidate

    def read_file(self, session_id: str, relative_path: str) -> str:
        root = self._require_workspace(session_id)
        target = self._resolve_path(root, relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return target.read_text(encoding="utf-8")

    def write_file(self, session_id: str, relative_path: str, content: str) -> bool:
        root = self._require_workspace(session_id)
        target = self._resolve_path(root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True

    def list_tree(self, session_id: str, relative_path: str = "") -> list[dict[str, Any]]:
        root = self._require_workspace(session_id)
        target = self._resolve_path(root, relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {relative_path}")
        if target.is_file():
            raise NotADirectoryError(f"Path is a file: {relative_path}")

        entries: list[dict[str, Any]] = []
        for child in sorted(
            target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
        ):
            rel = child.relative_to(root).as_posix()
            entries.append(
                {
                    "name": child.name,
                    "path": rel,
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else 0,
                }
            )
        return entries

