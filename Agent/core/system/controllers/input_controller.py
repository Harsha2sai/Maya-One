from __future__ import annotations

import time

from core.system.os_controller import get_os_controller
from core.system.rate_limiter import SystemRateLimiter
from core.system.safe_shell import safe_shell
from core.system.system_models import SystemAction, SystemActionType, SystemResult


class InputController:
    def execute(self, action: SystemAction) -> SystemResult:
        handlers = {
            SystemActionType.MOUSE_CLICK: self.mouse_click,
            SystemActionType.MOUSE_MOVE: self.mouse_move,
            SystemActionType.KEY_PRESS: self.key_press,
            SystemActionType.TYPE_TEXT: self.type_text,
        }
        handler = handlers.get(action.action_type)
        if handler is None:
            return SystemResult(False, action.action_type, "Unsupported input action.", trace_id=action.trace_id)
        return handler(action)

    def mouse_click(self, action: SystemAction) -> SystemResult:
        controller = get_os_controller()
        SystemRateLimiter.check_click()
        button = int(action.params.get("button") or 1)
        if controller.get_display_server() == "xdotool":
            ok, output = safe_shell(f"xdotool click {button}")
        else:
            ok, output = safe_shell(f"ydotool click {button}")
        time.sleep(0.2)
        return SystemResult(ok, action.action_type, "Clicked." if ok else "Unable to click.", detail=output, trace_id=action.trace_id)

    def mouse_move(self, action: SystemAction) -> SystemResult:
        controller = get_os_controller()
        x = int(action.params.get("x") or 0)
        y = int(action.params.get("y") or 0)
        if controller.get_display_server() == "xdotool":
            ok, output = safe_shell(f"xdotool mousemove {x} {y}")
        else:
            ok, output = safe_shell(f"ydotool mousemove --absolute {x} {y}")
        time.sleep(0.2)
        return SystemResult(ok, action.action_type, "Moved pointer." if ok else "Unable to move pointer.", detail=output, trace_id=action.trace_id)

    def key_press(self, action: SystemAction) -> SystemResult:
        controller = get_os_controller()
        key = str(action.params.get("key") or "").strip()
        if controller.get_display_server() == "xdotool":
            ok, output = safe_shell(f"xdotool key {key}")
        else:
            ok, output = safe_shell(f"ydotool key {key}")
        time.sleep(0.2)
        return SystemResult(ok, action.action_type, "Pressed key." if ok else "Unable to press key.", detail=output, trace_id=action.trace_id)

    def type_text(self, action: SystemAction) -> SystemResult:
        controller = get_os_controller()
        text = str(action.params.get("text") or "").replace("'", "'\"'\"'")
        if controller.get_display_server() == "xdotool":
            ok, output = safe_shell(f"xdotool type --clearmodifiers '{text}'")
        else:
            ok, output = safe_shell(f"wtype '{text}'")
        time.sleep(0.2)
        return SystemResult(ok, action.action_type, "Typed text." if ok else "Unable to type text.", detail=output, trace_id=action.trace_id)
