from __future__ import annotations

import os
from shutil import which

from core.system.safe_shell import safe_shell
from core.system.system_models import SystemAction, SystemActionType, SystemResult


class AppController:
    def execute(self, action: SystemAction) -> SystemResult:
        handlers = {
            SystemActionType.APP_LAUNCH: self.launch,
            SystemActionType.APP_CLOSE: self.close,
            SystemActionType.APP_FOCUS: self.focus,
        }
        handler = handlers.get(action.action_type)
        if handler is None:
            return SystemResult(False, action.action_type, "Unsupported app action.", trace_id=action.trace_id)
        return handler(action)

    def launch(self, action: SystemAction) -> SystemResult:
        app_name = str(action.params.get("app_name") or "").strip()
        if not app_name:
            return SystemResult(False, action.action_type, "Missing app name.", trace_id=action.trace_id)
        installed_apps = action.params.get("installed_apps") or {}
        command = ""
        if isinstance(installed_apps, dict):
            command = str(installed_apps.get(app_name.lower()) or "").strip()
        if not command and os.path.isabs(app_name) and os.path.exists(app_name):
            command = app_name
        if not command and which(app_name):
            command = app_name
        if not command:
            ok, output = safe_shell(f"xdg-open '{app_name}'")
            return SystemResult(ok, action.action_type, f"Opened {app_name}." if ok else "Unable to open app.", detail=output, trace_id=action.trace_id)
        ok, output = safe_shell(command)
        return SystemResult(ok, action.action_type, f"Opened {app_name}." if ok else "Unable to open app.", detail=output, trace_id=action.trace_id)

    def close(self, action: SystemAction) -> SystemResult:
        window_title = str(action.params.get("app_name") or action.params.get("window_title") or "").strip()
        ok, output = safe_shell(f'wmctrl -c "{window_title}"')
        return SystemResult(ok, action.action_type, f"Closed {window_title}." if ok else "Unable to close app.", detail=output, trace_id=action.trace_id)

    def focus(self, action: SystemAction) -> SystemResult:
        window_title = str(action.params.get("app_name") or action.params.get("window_title") or "").strip()
        ok, output = safe_shell(f'wmctrl -a "{window_title}"')
        return SystemResult(ok, action.action_type, f"Focused {window_title}." if ok else "Unable to focus app.", detail=output, trace_id=action.trace_id)
