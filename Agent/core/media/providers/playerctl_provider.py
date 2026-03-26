from __future__ import annotations

import logging

from tools.system.pc_control import run_shell_command

from core.media.media_models import MediaCommand, MediaResult
from core.media.providers.base_provider import BaseMediaProvider

logger = logging.getLogger(__name__)


class PlayerctlProvider(BaseMediaProvider):
    name = "playerctl"

    async def can_handle(self, command: MediaCommand, user_id: str) -> bool:  # noqa: ARG002
        return command.action in {
            "play",
            "pause",
            "resume",
            "stop",
            "next",
            "previous",
            "status",
            "search",
            "recommend",
            "queue",
            "current",
        }

    async def execute(self, command: MediaCommand, user_id: str) -> MediaResult:  # noqa: ARG002
        mapping = {
            "play": "playerctl play",
            "pause": "playerctl pause",
            "resume": "playerctl play",
            "stop": "playerctl stop",
            "next": "playerctl next",
            "previous": "playerctl previous",
            "status": "playerctl status",
            "current": "playerctl metadata --format '{{ title }} - {{ artist }}'",
        }
        shell_cmd = mapping.get(command.action)
        if not shell_cmd:
            fallback_cmd = "playerctl play"
            try:
                output = await run_shell_command(None, fallback_cmd)
                return MediaResult(
                    success=True,
                    action=command.action,
                    provider=self.name,
                    message=str(output or "Starting playback."),
                )
            except Exception as e:
                logger.warning("playerctl_provider_generic_play_failed action=%s error=%s", command.action, e)
                return MediaResult(
                    success=False,
                    action=command.action,
                    provider=self.name,
                    message="I was unable to complete that.",
                )

        try:
            output = await run_shell_command(None, shell_cmd)
            output_text = str(output or "").strip()
            if "no player could handle this command" in output_text.lower():
                return MediaResult(
                    success=False,
                    action=command.action,
                    provider=self.name,
                    message="No active media player was detected.",
                )
            return MediaResult(
                success=True,
                action=command.action,
                provider=self.name,
                message=output_text or "Starting playback.",
            )
        except Exception as e:
            logger.warning("playerctl_provider_execution_failed action=%s error=%s", command.action, e)
            return MediaResult(
                success=False,
                action=command.action,
                provider=self.name,
                message="I was unable to complete that.",
            )
