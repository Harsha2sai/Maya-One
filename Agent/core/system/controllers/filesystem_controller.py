from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from core.system.action_journal import ActionJournal
from core.system.system_models import SystemAction, SystemActionType, SystemResult


class FileSystemController:
    def execute(self, action: SystemAction) -> SystemResult:
        handlers = {
            SystemActionType.FILE_CREATE: self.create,
            SystemActionType.FILE_MOVE: self.move,
            SystemActionType.FILE_COPY: self.copy,
            SystemActionType.FILE_DELETE: self.delete,
            SystemActionType.FILE_SEARCH: self.search,
            SystemActionType.FILE_ORGANIZE: self.organize,
            SystemActionType.FILE_RENAME: self.rename,
        }
        handler = handlers.get(action.action_type)
        if handler is None:
            return SystemResult(False, action.action_type, "Unsupported file action.", trace_id=action.trace_id)
        return handler(action)

    def create(self, action: SystemAction) -> SystemResult:
        path = Path(os.path.expanduser(str(action.params.get("path") or "")))
        is_directory = bool(action.params.get("directory"))
        if not str(path):
            return SystemResult(False, action.action_type, "Missing target path.", trace_id=action.trace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if is_directory:
            path.mkdir(exist_ok=True)
            message = f"Created folder {path.name}."
        else:
            path.touch(exist_ok=True)
            message = f"Created file {path.name}."
        return SystemResult(True, action.action_type, message, detail=str(path), trace_id=action.trace_id)

    def move(self, action: SystemAction) -> SystemResult:
        source = os.path.expanduser(str(action.params.get("source") or ""))
        destination = os.path.expanduser(str(action.params.get("destination") or ""))
        if not source or not destination:
            return SystemResult(False, action.action_type, "Missing source or destination.", trace_id=action.trace_id)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)
        return SystemResult(True, action.action_type, f"Moved {os.path.basename(source)}.", detail=destination, trace_id=action.trace_id)

    def copy(self, action: SystemAction) -> SystemResult:
        source = os.path.expanduser(str(action.params.get("source") or ""))
        destination = os.path.expanduser(str(action.params.get("destination") or ""))
        if not source or not destination:
            return SystemResult(False, action.action_type, "Missing source or destination.", trace_id=action.trace_id)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)
        return SystemResult(True, action.action_type, f"Copied {os.path.basename(source)}.", detail=destination, trace_id=action.trace_id)

    def delete(self, action: SystemAction) -> SystemResult:
        path = os.path.expanduser(str(action.params.get("path") or ""))
        if not path or not os.path.exists(path):
            return SystemResult(False, action.action_type, "File not found.", trace_id=action.trace_id)
        trashed, trash_path = ActionJournal.move_to_trash(path)
        if not trashed:
            return SystemResult(False, action.action_type, "Unable to stage file for deletion.", trace_id=action.trace_id)
        action.params["trash_path"] = trash_path
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return SystemResult(True, action.action_type, f"Deleted {os.path.basename(path)}.", rollback_available=True, trace_id=action.trace_id)

    def search(self, action: SystemAction) -> SystemResult:
        root = Path(os.path.expanduser(str(action.params.get("path") or "~")))
        pattern = str(action.params.get("query") or action.params.get("pattern") or "").lower()
        if not pattern:
            return SystemResult(False, action.action_type, "Missing search query.", trace_id=action.trace_id)
        max_depth = int(action.params.get("max_depth") or 5)
        started = time.time()
        matches: list[str] = []
        for current_root, dirnames, filenames in os.walk(root):
            depth = len(Path(current_root).relative_to(root).parts)
            if depth >= max_depth:
                dirnames[:] = []
            if time.time() - started > 10:
                break
            for name in filenames + dirnames:
                if pattern in name.lower():
                    matches.append(str(Path(current_root) / name))
        detail = "\n".join(matches[:20])
        return SystemResult(True, action.action_type, f"Found {len(matches)} matches.", detail=detail, trace_id=action.trace_id)

    def organize(self, action: SystemAction) -> SystemResult:
        root = Path(os.path.expanduser(str(action.params.get("path") or "")))
        if not root.exists():
            return SystemResult(False, action.action_type, "Folder not found.", trace_id=action.trace_id)
        moved = 0
        for item in root.iterdir():
            if item.is_dir():
                continue
            folder_name = (item.suffix.lower().lstrip(".") or "other")
            target_dir = root / folder_name
            target_dir.mkdir(exist_ok=True)
            shutil.move(str(item), str(target_dir / item.name))
            moved += 1
        return SystemResult(True, action.action_type, f"Organized {moved} files.", detail=str(root), trace_id=action.trace_id)

    def rename(self, action: SystemAction) -> SystemResult:
        path = Path(os.path.expanduser(str(action.params.get("path") or "")))
        new_name = str(action.params.get("new_name") or "").strip()
        if not path.exists() or not new_name:
            return SystemResult(False, action.action_type, "Missing file or new name.", trace_id=action.trace_id)
        target = path.with_name(new_name)
        shutil.move(str(path), str(target))
        action.params["old_path"] = str(path)
        action.params["new_path"] = str(target)
        action.params["renamed_path"] = str(target)
        return SystemResult(True, action.action_type, f"Renamed to {new_name}.", rollback_available=True, trace_id=action.trace_id)
