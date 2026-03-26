from __future__ import annotations

from core.system.os_controller import get_os_controller
from core.system.safe_shell import safe_shell
from core.system.system_models import SystemAction, SystemActionType, SystemResult


class WindowController:
    def execute(self, action: SystemAction) -> SystemResult:
        handlers = {
            SystemActionType.WINDOW_MOVE: self.move,
            SystemActionType.WINDOW_RESIZE: self.resize,
            SystemActionType.WINDOW_MINIMIZE: self.minimize,
            SystemActionType.WINDOW_MAXIMIZE: self.maximize,
        }
        handler = handlers.get(action.action_type)
        if handler is None:
            return SystemResult(False, action.action_type, "Unsupported window action.", trace_id=action.trace_id)
        return handler(action)

    def list_windows(self, action: SystemAction | None = None) -> SystemResult:
        ok, output = safe_shell("wmctrl -l")
        trace_id = action.trace_id if action else ""
        return SystemResult(ok, SystemActionType.WINDOW_MOVE, "Listed windows." if ok else "Unable to list windows.", detail=output, trace_id=trace_id)

    def move(self, action: SystemAction) -> SystemResult:
        controller = get_os_controller()
        x = int(action.params.get("x") or 0)
        y = int(action.params.get("y") or 0)
        if controller.get_display_server() == "xdotool":
            ok, output = safe_shell(f"xdotool getactivewindow windowmove {x} {y}")
        else:
            ok, output = safe_shell(f"wmctrl -r :ACTIVE: -e 0,{x},{y},-1,-1")
        return SystemResult(ok, action.action_type, "Moved window." if ok else "Unable to move window.", detail=output, trace_id=action.trace_id)

    def resize(self, action: SystemAction) -> SystemResult:
        controller = get_os_controller()
        width = int(action.params.get("width") or 800)
        height = int(action.params.get("height") or 600)
        if controller.get_display_server() == "xdotool":
            ok, output = safe_shell(f"xdotool getactivewindow windowsize {width} {height}")
        else:
            ok, output = safe_shell(f"wmctrl -r :ACTIVE: -e 0,-1,-1,{width},{height}")
        return SystemResult(ok, action.action_type, "Resized window." if ok else "Unable to resize window.", detail=output, trace_id=action.trace_id)

    def minimize(self, action: SystemAction) -> SystemResult:
        ok, output = safe_shell("wmctrl -r :ACTIVE: -b add,hidden")
        return SystemResult(ok, action.action_type, "Minimized window." if ok else "Unable to minimize window.", detail=output, trace_id=action.trace_id)

    def maximize(self, action: SystemAction) -> SystemResult:
        ok, output = safe_shell("wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz")
        return SystemResult(ok, action.action_type, "Maximized window." if ok else "Unable to maximize window.", detail=output, trace_id=action.trace_id)
