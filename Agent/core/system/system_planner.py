from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any

from .action_journal import ActionJournal
from .action_trace import ActionTrace
from .action_validator import ActionValidator
from .confirmation_gate import ConfirmationGate
from .controllers import (
    AppController,
    FileSystemController,
    InputController,
    ProcessController,
    VisionController,
    WindowController,
)
from .rate_limiter import SystemRateLimiter
from .safe_shell import safe_shell
from .system_models import ConfirmationState, SystemAction, SystemActionType, SystemResult
from .system_state_cache import SystemStateCache

logger = logging.getLogger(__name__)


class SystemPlanner:
    MAX_LOOP_STEPS = 10

    def __init__(self) -> None:
        self.validator = ActionValidator()
        self.file_controller = FileSystemController()
        self.app_controller = AppController()
        self.window_controller = WindowController()
        self.input_controller = InputController()
        self.process_controller = ProcessController()
        self.vision_controller = VisionController()

    async def plan_and_execute(self, intent: str, session: Any = None, trace_id: str = "") -> SystemResult:
        actions = await self._parse_intent(intent, trace_id=trace_id)
        if not actions:
            return SystemResult(
                success=False,
                action_type=SystemActionType.VISION_QUERY,
                message="I couldn't determine a safe system action for that request.",
                trace_id=trace_id,
            )

        ok, msg = SystemRateLimiter.check_task()
        if not ok:
            return SystemResult(False, actions[0].action_type, msg, trace_id=trace_id)

        if len(actions) <= 2:
            return await self._execute_single_shot(actions, session)
        return await self._execute_oscar_loop(actions, session)

    async def _execute_single_shot(self, actions: list[SystemAction], session: Any) -> SystemResult:
        return await self._execute_oscar_loop(actions, session)

    async def _execute_oscar_loop(self, actions: list[SystemAction], session: Any) -> SystemResult:
        results: list[SystemResult] = []
        for action in actions[: self.MAX_LOOP_STEPS]:
            if SystemStateCache.already_done(action):
                continue

            ok, reason = self.validator.validate(action)
            if not ok:
                return SystemResult(False, action.action_type, "I can't do that safely.", detail=reason, trace_id=action.trace_id)

            state = await ConfirmationGate.request(action, session)
            if state != ConfirmationState.CONFIRMED:
                return SystemResult(False, action.action_type, "Action cancelled.", detail=state.value, trace_id=action.trace_id)

            ok, msg = SystemRateLimiter.check_action(action.trace_id)
            if not ok:
                return SystemResult(False, action.action_type, msg, trace_id=action.trace_id)

            started = time.time()
            result = await self._route_to_controller(action)
            duration_ms = (time.time() - started) * 1000
            screenshot_path = result.detail if action.action_type == SystemActionType.SCREENSHOT and result.success else ""

            ActionJournal.record(action, result)
            ActionTrace.record(action, result, screenshot_path=screenshot_path, duration_ms=duration_ms)
            SystemStateCache.record(action)
            SystemRateLimiter.increment_action()
            results.append(result)

            await asyncio.sleep(0.2)
            if not result.success:
                break

        return self._summarize_results(results, actions)

    async def _route_to_controller(self, action: SystemAction) -> SystemResult:
        if action.action_type in {
            SystemActionType.FILE_CREATE,
            SystemActionType.FILE_MOVE,
            SystemActionType.FILE_COPY,
            SystemActionType.FILE_DELETE,
            SystemActionType.FILE_SEARCH,
            SystemActionType.FILE_ORGANIZE,
            SystemActionType.FILE_RENAME,
        }:
            return self.file_controller.execute(action)
        if action.action_type in {
            SystemActionType.APP_LAUNCH,
            SystemActionType.APP_CLOSE,
            SystemActionType.APP_FOCUS,
        }:
            return self.app_controller.execute(action)
        if action.action_type in {
            SystemActionType.WINDOW_MOVE,
            SystemActionType.WINDOW_RESIZE,
            SystemActionType.WINDOW_MINIMIZE,
            SystemActionType.WINDOW_MAXIMIZE,
        }:
            return self.window_controller.execute(action)
        if action.action_type in {
            SystemActionType.MOUSE_CLICK,
            SystemActionType.MOUSE_MOVE,
            SystemActionType.KEY_PRESS,
            SystemActionType.TYPE_TEXT,
        }:
            return self.input_controller.execute(action)
        if action.action_type in {SystemActionType.PROCESS_LIST, SystemActionType.PROCESS_KILL}:
            return self.process_controller.execute(action)
        if action.action_type == SystemActionType.SHELL_COMMAND:
            ok, output = safe_shell(str(action.params.get("command") or ""))
            return SystemResult(
                ok,
                action.action_type,
                output or ("Command completed." if ok else "I can't do that safely."),
                detail="" if ok else output,
                trace_id=action.trace_id,
            )
        if action.action_type in {SystemActionType.SCREENSHOT, SystemActionType.VISION_QUERY}:
            return self.vision_controller.execute(action)
        return SystemResult(False, action.action_type, "Unsupported system action.", trace_id=action.trace_id)

    async def _parse_intent(self, intent: str, trace_id: str = "") -> list[SystemAction]:
        text = str(intent or "").strip()
        normalized = re.sub(r"\s+", " ", text.lower())
        actions: list[SystemAction] = []

        command_match = re.search(r"^(?:run|execute)\s+(.+)$", text, flags=re.IGNORECASE)
        if command_match:
            actions.append(
                SystemAction(
                    SystemActionType.SHELL_COMMAND,
                    params={"command": command_match.group(1).strip()},
                    trace_id=trace_id,
                )
            )
            return actions

        if "rm -rf /" in normalized:
            actions.append(
                SystemAction(
                    action_type=SystemActionType.SHELL_COMMAND,
                    params={"command": "rm -rf /"},
                    destructive=True,
                    trace_id=trace_id,
                )
            )
            return actions

        if "take a screenshot" in normalized or normalized.startswith("screenshot"):
            actions.append(SystemAction(SystemActionType.SCREENSHOT, trace_id=trace_id))
            return actions

        delete_match = re.search(r"(?:delete|remove)\s+(?:the\s+)?file\s+(.+)$", normalized)
        if delete_match:
            raw_path = delete_match.group(1).strip().strip("'\"")
            path = raw_path if raw_path.startswith("/") else os.path.join(os.getcwd(), raw_path)
            actions.append(
                SystemAction(
                    SystemActionType.FILE_DELETE,
                    params={"path": path},
                    destructive=True,
                    requires_confirmation=True,
                    trace_id=trace_id,
                )
            )
            return actions

        rename_match = re.search(r"rename\s+(.+?)\s+to\s+(.+)$", text, flags=re.IGNORECASE)
        if rename_match:
            source = rename_match.group(1).strip().strip("'\"")
            new_name = rename_match.group(2).strip().strip("'\"")
            path = source if source.startswith("/") else os.path.join(os.getcwd(), source)
            actions.append(
                SystemAction(
                    SystemActionType.FILE_RENAME,
                    params={"path": path, "new_name": new_name},
                    destructive=True,
                    requires_confirmation=True,
                    trace_id=trace_id,
                )
            )
            return actions

        move_match = re.search(r"move\s+(.+?)\s+to\s+(.+)$", text, flags=re.IGNORECASE)
        if move_match:
            source = move_match.group(1).strip().strip("'\"")
            destination = move_match.group(2).strip().strip("'\"")
            actions.append(
                SystemAction(
                    SystemActionType.FILE_MOVE,
                    params={
                        "source": source if source.startswith("/") else os.path.join(os.getcwd(), source),
                        "destination": destination if destination.startswith("/") else os.path.join(os.getcwd(), destination),
                    },
                    trace_id=trace_id,
                )
            )
            return actions

        copy_match = re.search(r"copy\s+(.+?)\s+to\s+(.+)$", text, flags=re.IGNORECASE)
        if copy_match:
            source = copy_match.group(1).strip().strip("'\"")
            destination = copy_match.group(2).strip().strip("'\"")
            actions.append(
                SystemAction(
                    SystemActionType.FILE_COPY,
                    params={
                        "source": source if source.startswith("/") else os.path.join(os.getcwd(), source),
                        "destination": destination if destination.startswith("/") else os.path.join(os.getcwd(), destination),
                    },
                    trace_id=trace_id,
                )
            )
            return actions

        create_file = re.search(r"create\s+(?:a\s+)?file\s+(.+)$", text, flags=re.IGNORECASE)
        if create_file:
            path = create_file.group(1).strip().strip("'\"")
            actions.append(
                SystemAction(
                    SystemActionType.FILE_CREATE,
                    params={"path": path if path.startswith("/") else os.path.join(os.getcwd(), path)},
                    trace_id=trace_id,
                )
            )
            return actions

        if "organize" in normalized and any(name in normalized for name in ("downloads", "desktop", "folder")):
            target = os.path.expanduser("~/Downloads" if "downloads" in normalized else "~/Desktop")
            actions.append(SystemAction(SystemActionType.FILE_ORGANIZE, params={"path": target}, trace_id=trace_id))
            return actions

        find_file = re.search(r"(?:find|search for)\s+file\s+(.+)$", text, flags=re.IGNORECASE)
        if find_file:
            query = find_file.group(1).strip()
            actions.append(
                SystemAction(
                    SystemActionType.FILE_SEARCH,
                    params={"path": os.path.expanduser("~"), "query": query},
                    trace_id=trace_id,
                )
            )
            return actions

        click_match = re.search(r"click\s+(?:on\s+)?(.+)$", text, flags=re.IGNORECASE)
        if click_match:
            actions.append(
                SystemAction(
                    SystemActionType.VISION_QUERY,
                    params={"description": click_match.group(1).strip()},
                    trace_id=trace_id,
                )
            )
            actions.append(SystemAction(SystemActionType.MOUSE_CLICK, trace_id=trace_id))
            return actions

        type_match = re.search(r"(?:type|write|enter)\s+(.+)$", text, flags=re.IGNORECASE)
        if type_match:
            actions.append(SystemAction(SystemActionType.TYPE_TEXT, params={"text": type_match.group(1).strip()}, trace_id=trace_id))
            return actions

        if any(word in normalized for word in ("minimize window", "maximize window", "resize window", "move window")):
            if "minimize" in normalized:
                actions.append(SystemAction(SystemActionType.WINDOW_MINIMIZE, trace_id=trace_id))
            elif "maximize" in normalized:
                actions.append(SystemAction(SystemActionType.WINDOW_MAXIMIZE, trace_id=trace_id))
            elif "resize" in normalized:
                actions.append(
                    SystemAction(
                        SystemActionType.WINDOW_RESIZE,
                        params={"width": 1280, "height": 720},
                        trace_id=trace_id,
                    )
                )
            else:
                actions.append(SystemAction(SystemActionType.WINDOW_MOVE, params={"x": 0, "y": 0}, trace_id=trace_id))
            return actions

        kill_match = re.search(r"kill\s+(?:process|app)?\s*(.+)$", text, flags=re.IGNORECASE)
        if kill_match:
            target = kill_match.group(1).strip().strip("'\"")
            actions.append(
                SystemAction(
                    SystemActionType.PROCESS_KILL,
                    params={"pid_or_name": target},
                    destructive=True,
                    requires_confirmation=True,
                    trace_id=trace_id,
                )
            )
            return actions

        if "list processes" in normalized:
            actions.append(SystemAction(SystemActionType.PROCESS_LIST, trace_id=trace_id))
            return actions

        if re.search(
            r"\bwhat\s+(?:windows|apps|applications)\s+are\s+(?:open|running|active)\b",
            normalized,
        ) or re.search(r"\blist\s+(?:open|running|active)\s+(?:windows|apps|applications)\b", normalized):
            actions.append(
                SystemAction(
                    SystemActionType.SHELL_COMMAND,
                    params={"command": "wmctrl -l"},
                    trace_id=trace_id,
                )
            )
            return actions

        if re.search(r"\b(list|show)\s+(?:running\s+)?processes\b", normalized) or re.search(
            r"\bwhat\s+(?:is|are)\s+running\b",
            normalized,
        ):
            actions.append(
                SystemAction(
                    SystemActionType.SHELL_COMMAND,
                    params={"command": "ps -eo pid,comm --sort=comm | head -n 40"},
                    trace_id=trace_id,
                )
            )
            return actions

        if normalized.startswith("what is on my screen") or normalized.startswith("what's on my screen"):
            actions.append(
                SystemAction(
                    SystemActionType.VISION_QUERY,
                    params={"question": "Describe what is on my screen"},
                    trace_id=trace_id,
                )
            )
            return actions

        return actions

    def _summarize_results(
        self,
        results: list[SystemResult],
        actions: list[SystemAction],
    ) -> SystemResult:
        if not results:
            first_action = actions[0] if actions else SystemAction(SystemActionType.VISION_QUERY)
            return SystemResult(False, first_action.action_type, "No system action was executed.", trace_id=first_action.trace_id)
        if len(results) == 1:
            return results[0]
        success_count = sum(1 for result in results if result.success)
        detail = "\n".join(result.message for result in results)
        return SystemResult(
            success=all(result.success for result in results),
            action_type=results[-1].action_type,
            message=f"Completed {success_count} of {len(results)} system actions.",
            detail=detail,
            trace_id=results[-1].trace_id,
        )
