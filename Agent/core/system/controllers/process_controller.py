from __future__ import annotations

import os
import signal
import subprocess

from core.system.system_models import SystemAction, SystemActionType, SystemResult

PROCESS_KILL_DENYLIST = {
    "systemd",
    "dbus",
    "dbus-daemon",
    "Xorg",
    "X",
    "gnome-shell",
    "wayland",
    "pulseaudio",
    "pipewire",
    "NetworkManager",
    "sshd",
    "init",
    "kthreadd",
}


class ProcessController:
    def execute(self, action: SystemAction) -> SystemResult:
        if action.action_type == SystemActionType.PROCESS_LIST:
            return self.list_processes(action)
        if action.action_type == SystemActionType.PROCESS_KILL:
            return self.kill_process(action)
        return SystemResult(False, action.action_type, "Unsupported process action.", trace_id=action.trace_id)

    def list_processes(self, action: SystemAction) -> SystemResult:
        result = subprocess.run(
            ["ps", "-eo", "pid,comm"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return SystemResult(
            result.returncode == 0,
            action.action_type,
            "Listed processes." if result.returncode == 0 else "Unable to list processes.",
            detail=(result.stdout or result.stderr).strip(),
            trace_id=action.trace_id,
        )

    def kill_process(self, action: SystemAction) -> SystemResult:
        target = str(action.params.get("pid_or_name") or action.params.get("name") or action.params.get("pid") or "").strip()
        if not target:
            return SystemResult(False, action.action_type, "Missing process target.", trace_id=action.trace_id)

        if target.isdigit():
            name = self._name_for_pid(int(target))
            pid = int(target)
        else:
            pid, name = self._find_pid_by_name(target)

        if not pid or not name:
            return SystemResult(False, action.action_type, "Process not found.", trace_id=action.trace_id)
        if name in PROCESS_KILL_DENYLIST:
            return SystemResult(
                False,
                action.action_type,
                "I can't kill that process - it's critical to your system",
                trace_id=action.trace_id,
            )

        os.kill(pid, signal.SIGTERM)
        return SystemResult(True, action.action_type, f"Sent SIGTERM to {name}.", trace_id=action.trace_id)

    def _find_pid_by_name(self, target: str) -> tuple[int | None, str | None]:
        result = subprocess.run(
            ["ps", "-eo", "pid=,comm="],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in (result.stdout or "").splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            pid, name = parts
            if target.lower() == name.lower():
                return int(pid), name
        return None, None

    def _name_for_pid(self, pid: int) -> str:
        try:
            with open(f"/proc/{pid}/comm", "r", encoding="utf-8") as handle:
                return handle.read().strip()
        except Exception:
            return ""
