"""Built-in file operations skill for list/read/write actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..base import BaseSkill, SkillPermissionLevel, SkillResult


class FileOperationsSkill(BaseSkill):
    def __init__(self, *, base_path: Optional[str] = None, allow_write: bool = True) -> None:
        super().__init__(
            name="file_operations",
            description="List, read, and write files in a constrained workspace",
            permission_level=SkillPermissionLevel.SYSTEM,
            permission_tool_name="open_app",
        )
        self._base_path = Path(base_path).expanduser().resolve() if base_path else None
        self._allow_write = bool(allow_write)

    def validate(self, params: Dict[str, Any]) -> bool:
        if not super().validate(params):
            return False
        operation = str((params or {}).get("operation") or "").strip().lower()
        if operation not in {"list", "read", "write"}:
            return False
        if operation in {"read", "write"}:
            return bool(str((params or {}).get("path") or "").strip())
        return True

    async def execute(self, params: Dict[str, Any]) -> SkillResult:
        operation = str((params or {}).get("operation") or "").strip().lower()
        target_path = str((params or {}).get("path") or ".").strip()

        try:
            resolved = self._resolve_path(target_path)
        except Exception as exc:
            return SkillResult(success=False, error=f"invalid_path:{exc}")

        if operation == "list":
            if not resolved.exists() or not resolved.is_dir():
                return SkillResult(success=False, error="path_not_directory")
            entries = sorted(item.name for item in resolved.iterdir())
            return SkillResult(success=True, data={"entries": entries, "path": str(resolved)})

        if operation == "read":
            if not resolved.exists() or not resolved.is_file():
                return SkillResult(success=False, error="file_not_found")
            content = resolved.read_text(encoding="utf-8")
            return SkillResult(success=True, data={"path": str(resolved), "content": content})

        if operation == "write":
            if not self._allow_write:
                return SkillResult(success=False, error="write_not_allowed")
            content = str((params or {}).get("content") or "")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return SkillResult(success=True, data={"path": str(resolved), "bytes": len(content.encode("utf-8"))})

        return SkillResult(success=False, error="unsupported_operation")

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute() and self._base_path is not None:
            candidate = self._base_path / candidate

        resolved = candidate.resolve()
        if self._base_path is not None:
            try:
                resolved.relative_to(self._base_path)
            except ValueError as exc:
                raise ValueError("path escapes base_path") from exc
        return resolved
