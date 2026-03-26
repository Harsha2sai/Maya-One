from __future__ import annotations

import json
import logging
from typing import Any

from core.system.screenshot_limiter import ScreenshotLimiter
from core.system.system_models import SystemAction, SystemActionType, SystemResult

logger = logging.getLogger(__name__)


class VisionController:
    def execute(self, action: SystemAction) -> SystemResult:
        if action.action_type == SystemActionType.SCREENSHOT:
            return self.screenshot(action)
        if action.action_type == SystemActionType.VISION_QUERY:
            return self.query_screen(action)
        return SystemResult(False, action.action_type, "Unsupported vision action.", trace_id=action.trace_id)

    def screenshot(self, action: SystemAction) -> SystemResult:
        ok, path = ScreenshotLimiter.take_screenshot()
        if not ok:
            return SystemResult(False, action.action_type, "Screenshot limit reached for this task.", trace_id=action.trace_id)
        return SystemResult(True, action.action_type, "Took a screenshot.", detail=path, trace_id=action.trace_id)

    def find_element(self, description: str) -> tuple[bool, dict[str, Any] | str]:
        atspi_result = self._find_via_atspi(description)
        if atspi_result:
            return True, atspi_result
        return self._find_via_vision(description)

    def query_screen(self, action: SystemAction) -> SystemResult:
        description = str(action.params.get("description") or action.params.get("question") or "").strip()
        ok, payload = self.find_element(description)
        if not ok:
            return SystemResult(False, action.action_type, str(payload), trace_id=action.trace_id)
        return SystemResult(True, action.action_type, "Located screen element.", detail=json.dumps(payload), trace_id=action.trace_id)

    def _find_via_atspi(self, description: str) -> dict[str, Any] | None:
        try:
            import pyatspi

            desktop = pyatspi.Registry.getDesktop(0)
            element = self._walk_tree(desktop, description.lower())
            if element is None:
                return None
            extents = element.queryComponent().getExtents(0)
            return {
                "x": extents.x,
                "y": extents.y,
                "width": extents.width,
                "height": extents.height,
                "confidence": 1.0,
            }
        except Exception as exc:
            logger.info("atspi_lookup_failed error=%s", exc)
            return None

    def _walk_tree(self, node: Any, description: str) -> Any:
        try:
            name = str(getattr(node, "name", "") or "").lower()
            role = str(getattr(getattr(node, "getRoleName", lambda: "")(), "lower", lambda: "")())
            if description and (description in name or description in role):
                return node
            child_count = int(getattr(node, "childCount", 0) or 0)
            for index in range(child_count):
                child = node[index]
                found = self._walk_tree(child, description)
                if found is not None:
                    return found
        except Exception:
            return None
        return None

    def _find_via_vision(self, description: str) -> tuple[bool, dict[str, Any] | str]:
        ok, screenshot_path = ScreenshotLimiter.take_screenshot()
        if not ok:
            return False, "Screenshot limit reached for this task"
        try:
            import google.generativeai as genai
        except Exception:
            return False, "I can't locate that element confidently enough to click it"

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = (
                f"Find the UI element: {description}. "
                'Return JSON: {"x": 0, "y": 0, "width": 0, "height": 0, "confidence": 0.0}'
            )
            response = model.generate_content([prompt, {"mime_type": "image/png", "data": open(screenshot_path, "rb").read()}])
            payload = json.loads(str(getattr(response, "text", "") or "{}"))
            confidence = float(payload.get("confidence") or 0.0)
            if confidence < 0.7:
                return False, "I can't locate that element confidently enough to click it"
            return True, payload
        except Exception:
            return False, "I can't locate that element confidently enough to click it"
