from unittest.mock import AsyncMock, MagicMock

import pytest

from core.media.media_agent import MediaAgent
from core.media.media_models import MediaResult


@pytest.mark.asyncio
async def test_media_agent_falls_back_to_playerctl() -> None:
    agent = MediaAgent()
    agent.spotify.can_handle = AsyncMock(return_value=False)
    agent.youtube.can_handle = AsyncMock(return_value=False)
    agent.playerctl.execute = AsyncMock(
        return_value=MediaResult(success=True, action="pause", provider="playerctl", message="Paused")
    )

    result = await agent.run(
        command="pause",
        user_id="u1",
        session_id="s1",
        trace_id="t1",
    )

    assert result.success is True
    assert result.provider == "playerctl"


@pytest.mark.asyncio
async def test_media_agent_completes_spotify_auth() -> None:
    agent = MediaAgent()
    agent.spotify_oauth.exchange_code = AsyncMock(
        return_value=MagicMock(access_token="a", refresh_token="r", expires_at=100, scope="s")
    )
    agent.spotify_token_store.save_tokens = MagicMock(return_value=True)

    ok = await agent.complete_spotify_auth(user_id="u1", code="abc", platform="mobile")
    assert ok is True


@pytest.mark.asyncio
async def test_media_agent_play_something_relaxing_does_not_return_unmapped_error() -> None:
    agent = MediaAgent()
    agent.spotify.can_handle = AsyncMock(return_value=False)
    agent.youtube.can_handle = AsyncMock(return_value=False)
    agent.playerctl.execute = AsyncMock(
        return_value=MediaResult(success=True, action="play", provider="playerctl", message="Starting playback.")
    )

    result = await agent.run(
        command="play something relaxing",
        user_id="u1",
        session_id="s1",
        trace_id="t1",
    )

    assert result.success is True
    assert "couldn't map that media command" not in result.message.lower()


@pytest.mark.asyncio
async def test_media_agent_opens_player_when_no_active_playerctl_target() -> None:
    agent = MediaAgent()
    agent.spotify.can_handle = AsyncMock(return_value=False)
    agent.youtube.can_handle = AsyncMock(return_value=False)
    agent.playerctl.execute = AsyncMock(
        return_value=MediaResult(
            success=False,
            action="play",
            provider="playerctl",
            message="No active media player was detected.",
        )
    )
    agent._open_music_player_fallback = AsyncMock(
        return_value=MediaResult(
            success=True,
            action="play",
            provider="fallback",
            message="Opening music player for something relaxing.",
        )
    )

    result = await agent.run(
        command="play something relaxing",
        user_id="u1",
        session_id="s1",
        trace_id="t1",
    )

    assert result.success is True
    assert "opening music player" in result.message.lower()
