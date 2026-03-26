from unittest.mock import AsyncMock, patch

import pytest

from core.media.media_models import MediaCommand
from core.media.providers.playerctl_provider import PlayerctlProvider


@pytest.mark.asyncio
async def test_playerctl_provider_executes_shell_command() -> None:
    provider = PlayerctlProvider()
    with patch("core.media.providers.playerctl_provider.run_shell_command", AsyncMock(return_value="ok")) as mock_run:
        result = await provider.execute(MediaCommand(action="pause"), user_id="u1")

    assert result.success is True
    assert result.provider == "playerctl"
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_playerctl_provider_supports_play_action() -> None:
    provider = PlayerctlProvider()
    with patch("core.media.providers.playerctl_provider.run_shell_command", AsyncMock(return_value="playing")):
        result = await provider.execute(MediaCommand(action="play"), user_id="u1")

    assert result.success is True
    assert "playing" in result.message.lower() or "starting playback" in result.message.lower()


@pytest.mark.asyncio
async def test_playerctl_provider_marks_no_player_output_as_failure() -> None:
    provider = PlayerctlProvider()
    with patch(
        "core.media.providers.playerctl_provider.run_shell_command",
        AsyncMock(return_value="STDERR:\nNo player could handle this command"),
    ):
        result = await provider.execute(MediaCommand(action="play"), user_id="u1")

    assert result.success is False
    assert "no active media player" in result.message.lower()
