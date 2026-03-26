from unittest.mock import AsyncMock

import pytest

from core.runtime.entrypoint import console_entrypoint
from core.runtime.global_agent import GlobalAgentContainer


@pytest.mark.asyncio
async def test_console_entrypoint_fast_path_skips_global_init(monkeypatch):
    monkeypatch.setattr(GlobalAgentContainer, "_initialized", False, raising=False)
    initialize = AsyncMock()
    handle_user_message = AsyncMock()
    monkeypatch.setattr(GlobalAgentContainer, "initialize", initialize, raising=False)
    monkeypatch.setattr(GlobalAgentContainer, "handle_user_message", handle_user_message, raising=False)

    await console_entrypoint("hello")

    initialize.assert_not_awaited()
    handle_user_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_console_entrypoint_non_fast_path_initializes_and_routes(monkeypatch):
    monkeypatch.setattr(GlobalAgentContainer, "_initialized", False, raising=False)
    initialize = AsyncMock()
    handle_user_message = AsyncMock(return_value={"display_text": "4"})
    monkeypatch.setattr(GlobalAgentContainer, "initialize", initialize, raising=False)
    monkeypatch.setattr(GlobalAgentContainer, "handle_user_message", handle_user_message, raising=False)

    await console_entrypoint("what is 2 + 2?")

    initialize.assert_awaited_once()
    handle_user_message.assert_awaited_once_with("what is 2 + 2?")
