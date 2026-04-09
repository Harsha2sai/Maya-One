from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agents.contracts import AgentCapabilityMatch, AgentHandoffResult
from core.agents.handoff_manager import HandoffManager
from core.agents.media_agent_handler import MediaAgentHandler
from core.media.media_models import MediaResult, MediaTrack
from core.orchestrator.agent_orchestrator import AgentOrchestrator


def _request(**overrides):
    payload = {
        "handoff_id": "handoff-media-1",
        "trace_id": "trace-media-1",
        "conversation_id": "conversation-1",
        "task_id": None,
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "media",
        "intent": "media_play",
        "user_text": "play some jazz music",
        "context_slice": "User asked for media playback.",
        "execution_mode": "inline",
        "delegation_depth": 0,
        "max_depth": 2,
        "handoff_reason": "router_media_play",
        "metadata": {"user_id": "u1", "platform": "desktop"},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


@pytest.mark.asyncio
async def test_media_handler_can_handle_media_play_intent():
    handler = MediaAgentHandler(media_agent=MagicMock())
    match = await handler.can_accept(_request())
    assert match.confidence == 1.0
    assert match.agent_name == "media"


@pytest.mark.asyncio
async def test_media_handler_cannot_handle_research_intent():
    handler = MediaAgentHandler(media_agent=MagicMock())
    match = await handler.can_accept(_request(intent="research", user_text="who is the PM"))
    assert match.confidence == 0.0


@pytest.mark.asyncio
async def test_media_handler_returns_normalized_result():
    fake_agent = MagicMock()
    fake_agent.is_spotify_connected = MagicMock(return_value=True)
    fake_agent.run = AsyncMock(
        return_value=MediaResult(
            success=True,
            action="play",
            provider="youtube",
            message="Playing jazz on YouTube.",
            track=MediaTrack(title="Jazz Mix", artist="Various", url="https://youtube.com/watch?v=abc"),
        )
    )
    handler = MediaAgentHandler(media_agent=fake_agent)

    result = await handler.handle(_request())

    assert result.status == "completed"
    assert result.structured_payload["provider"] == "youtube"
    assert result.structured_payload["track_name"] == "Jazz Mix"


@pytest.mark.asyncio
async def test_media_handler_spotify_requires_auth_returns_needs_followup():
    fake_agent = MagicMock()
    fake_agent.is_spotify_connected = MagicMock(return_value=False)
    fake_agent.spotify.prepare_spotify_auth = AsyncMock(
        return_value={"ok": True, "url": "https://spotify.example/auth", "state": "state-1", "platform": "desktop"}
    )
    handler = MediaAgentHandler(media_agent=fake_agent)

    result = await handler.handle(_request(user_text="play jazz on spotify"))

    assert result.status == "needs_followup"
    assert result.structured_payload["requires_auth"] is True
    assert result.structured_payload["url"] == "https://spotify.example/auth"


@pytest.mark.asyncio
async def test_media_handler_playerctl_pause_returns_completed():
    fake_agent = MagicMock()
    fake_agent.is_spotify_connected = MagicMock(return_value=False)
    fake_agent.run = AsyncMock(
        return_value=MediaResult(
            success=True,
            action="pause",
            provider="playerctl",
            message="Paused.",
        )
    )
    handler = MediaAgentHandler(media_agent=fake_agent)

    result = await handler.handle(_request(user_text="pause"))

    assert result.status == "completed"
    assert result.structured_payload["provider"] == "playerctl"
    assert result.structured_payload["action"] == "pause"


@pytest.mark.asyncio
async def test_media_handler_preserves_trace_id_and_handoff_id():
    fake_agent = MagicMock()
    fake_agent.is_spotify_connected = MagicMock(return_value=True)
    fake_agent.run = AsyncMock(
        return_value=MediaResult(success=True, action="play", provider="youtube", message="Playing.")
    )
    handler = MediaAgentHandler(media_agent=fake_agent)

    result = await handler.handle(_request(handoff_id="h-1", trace_id="t-1"))

    assert result.handoff_id == "h-1"
    assert result.trace_id == "t-1"


@pytest.mark.asyncio
async def test_handoff_manager_routes_media_to_media_handler():
    class _Registry:
        async def can_accept(self, request):
            return AgentCapabilityMatch(
                agent_name="media",
                confidence=1.0,
                reason="router_media_play_intent",
                hard_constraints_passed=True,
            )

        async def handle(self, request):
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent="media",
                status="completed",
                user_visible_text="Playing.",
                voice_text="Playing.",
                structured_payload={"action": "play", "provider": "youtube", "success": True},
                next_action="respond",
            )

    manager = HandoffManager(_Registry())
    result = await manager.delegate(_request())
    assert result.status == "completed"
    assert result.source_agent == "media"


@pytest.mark.asyncio
async def test_orchestrator_media_play_route_uses_handoff_manager():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="media_play")
    orchestrator._handoff_manager = MagicMock()
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="media")
    orchestrator._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            user_visible_text="Playing jazz on YouTube.",
            structured_payload={
                "action": "play",
                "provider": "youtube",
                "track_name": "Jazz Mix",
                "artist": "Various",
                "album_art_url": "",
                "track_url": "https://youtube.com/watch?v=abc",
                "trace_id": "trace-media-1",
                "success": True,
                "message": "Playing jazz on YouTube.",
            },
        )
    )

    response = await orchestrator._handle_chat_response("play some jazz music", user_id="u1", origin="chat")

    orchestrator._handoff_manager.delegate.assert_awaited_once()
    assert response.structured_data["_media_result"]["provider"] == "youtube"
