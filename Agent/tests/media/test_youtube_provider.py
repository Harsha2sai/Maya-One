from unittest.mock import AsyncMock, patch

import pytest

from core.media.media_models import MediaCommand
from core.media.providers.youtube_provider import YouTubeProvider


@pytest.mark.asyncio
async def test_youtube_provider_fallback_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    provider = YouTubeProvider()

    with patch("core.media.providers.youtube_provider.run_shell_command", AsyncMock(return_value="opened")) as mock_open:
        result = await provider.execute(MediaCommand(action="search", query="ai music"), user_id="u1")

    assert result.success is True
    mock_open.assert_awaited_once()


@pytest.mark.asyncio
async def test_youtube_provider_can_handle_video_text() -> None:
    provider = YouTubeProvider()
    assert await provider.can_handle(MediaCommand(action="search", query="video", raw_text="watch video"), "u1")
