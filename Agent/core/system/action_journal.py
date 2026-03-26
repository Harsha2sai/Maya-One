from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .system_models import SystemAction, SystemActionType, SystemResult

logger = logging.getLogger(__name__)

TRASH_DIR = "/tmp/maya_trash"


@dataclass
class JournalEntry:
    timestamp: str
    action: SystemAction
    result: SystemResult
    rollback_recipe: dict


class ActionJournal:
    _entries: list[JournalEntry] = []
    _max_entries: int = 50

    @classmethod
    def record(cls, action: SystemAction, result: SystemResult) -> JournalEntry:
        cls.cleanup_trash()
        recipe = cls._build_rollback(action)
        action.rollback_recipe = dict(recipe)
        entry = JournalEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            result=result,
            rollback_recipe=recipe,
        )
        cls._entries.append(entry)
        if len(cls._entries) > cls._max_entries:
            cls._entries.pop(0)
        return entry

    @classmethod
    def move_to_trash(cls, path: str) -> tuple[bool, str]:
        source = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(source):
            return False, ""
        os.makedirs(TRASH_DIR, exist_ok=True)
        target = os.path.join(TRASH_DIR, f"{int(time.time())}_{os.path.basename(source)}")
        shutil.copy2(source, target)
        return True, target

    @classmethod
    def rollback_last(cls) -> tuple[bool, str]:
        if not cls._entries:
            return False, "Nothing to roll back"
        last = cls._entries.pop()
        recipe = dict(last.rollback_recipe or {})
        if not recipe:
            return False, "No rollback available"

        action_type = str(recipe.get("type") or "")
        if action_type == "FILE_MOVE":
            source = str(recipe.get("from") or "")
            target = str(recipe.get("to") or "")
            if not source or not target:
                return False, "Rollback recipe is incomplete"
            shutil.move(source, target)
            return True, f"Moved {source} back to {target}"

        if action_type == "RESTORE":
            source = str(recipe.get("from") or "")
            target = str(recipe.get("to") or "")
            if not source or not target or not os.path.exists(source):
                return False, "Restore source is unavailable"
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
            return True, f"Restored {target}"

        if action_type == "FILE_RENAME":
            source = str(recipe.get("from") or "")
            target = str(recipe.get("to") or "")
            if not source or not target:
                return False, "Rename rollback recipe is incomplete"
            shutil.move(source, target)
            return True, f"Renamed {source} back to {target}"

        return False, "Unsupported rollback recipe"

    @classmethod
    def cleanup_trash(cls, max_age_seconds: int = 3600) -> None:
        if not os.path.isdir(TRASH_DIR):
            return
        now = time.time()
        for name in os.listdir(TRASH_DIR):
            path = os.path.join(TRASH_DIR, name)
            try:
                if now - os.path.getmtime(path) > max_age_seconds:
                    os.remove(path)
            except FileNotFoundError:
                continue
            except Exception as exc:
                logger.warning("trash_cleanup_failed path=%s error=%s", path, exc)

    @classmethod
    def _build_rollback(cls, action: SystemAction) -> dict:
        if action.rollback_recipe:
            return dict(action.rollback_recipe)

        params = action.params or {}
        if action.action_type == SystemActionType.FILE_MOVE:
            return {
                "type": "FILE_MOVE",
                "from": params.get("destination", ""),
                "to": params.get("source", ""),
            }
        if action.action_type == SystemActionType.FILE_DELETE:
            trash_path = str(params.get("trash_path") or "")
            path = str(params.get("path") or "")
            return {
                "type": "RESTORE",
                "from": trash_path,
                "to": path,
            }
        if action.action_type == SystemActionType.FILE_RENAME:
            source = str(params.get("renamed_path") or params.get("new_path") or "")
            target = str(params.get("path") or params.get("old_path") or "")
            return {
                "type": "FILE_RENAME",
                "from": source,
                "to": target,
            }
        return {}
