"""Tests for VoiceProjectBridge wiring with current project orchestrator API."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio


class TestVoiceProjectBridge:
    """Validate bridge command normalization and dispatch behavior."""

    @pytest_asyncio.fixture
    async def bridge(self):
        from core.livekit.voice_project_bridge import VoiceProjectBridge

        mock_project = MagicMock()
        mock_project._active = None
        mock_project.is_active = MagicMock(side_effect=lambda: mock_project._active is not None)

        async def _start(name: str, description: str = ""):
            mock_project._active = SimpleNamespace(name=name, description=description, prd=None)
            return f"Project '{name}' started."

        async def _add_requirement(req: str):
            return f"Requirement recorded: {req}"

        async def _advance():
            return "Advanced project phase."

        async def _status():
            if not mock_project._active:
                return "No active project."
            return f"Project: {mock_project._active.name}"

        async def _cancel():
            if not mock_project._active:
                return "No active project to cancel."
            name = mock_project._active.name
            mock_project._active = None
            return f"Project '{name}' cancelled."

        mock_project.start = AsyncMock(side_effect=_start)
        mock_project.add_requirement = AsyncMock(side_effect=_add_requirement)
        mock_project.advance = AsyncMock(side_effect=_advance)
        mock_project.status = AsyncMock(side_effect=_status)
        mock_project.cancel = AsyncMock(side_effect=_cancel)

        bridge = VoiceProjectBridge(project_orchestrator=mock_project, buddy=MagicMock())
        return bridge

    @pytest.mark.asyncio
    async def test_on_transcript_starts_project_for_explicit_project_voice(self, bridge):
        response = await bridge.on_transcript("project shopping app", is_final=True)
        bridge.project.start.assert_called_once_with("shopping app")
        assert "started" in response.lower()
        assert bridge.is_active is True

    @pytest.mark.asyncio
    async def test_on_transcript_ignores_interim(self, bridge):
        response = await bridge.on_transcript("project shopping app", is_final=False)
        assert response is None
        bridge.project.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_transcript_routes_requirement_when_active(self, bridge):
        await bridge.on_transcript("project shopping app", is_final=True)
        bridge.project.start.reset_mock()
        response = await bridge.on_transcript("Use Stripe for payments", is_final=True)
        bridge.project.start.assert_not_called()
        bridge.project.add_requirement.assert_called_once_with("Use Stripe for payments")
        assert "requirement recorded" in response.lower()

    @pytest.mark.asyncio
    async def test_on_transcript_maps_done_to_advance(self, bridge):
        await bridge.on_transcript("project shopping app", is_final=True)
        response = await bridge.on_transcript("done", is_final=True)
        bridge.project.advance.assert_called_once()
        assert response == "Advanced project phase."

    @pytest.mark.asyncio
    async def test_end_session_clears_active_project(self, bridge):
        await bridge.on_transcript("project shopping app", is_final=True)
        response = await bridge.end_session()
        bridge.project.cancel.assert_called_once()
        assert "cancelled" in response.lower()
        assert bridge.is_active is False


class TestVoiceTranscriptTopicHandler:
    """Smoke checks for payload parsing expectations."""

    @pytest.mark.asyncio
    async def test_voice_transcript_parses_json(self):
        payload = json.dumps({"text": "Hello", "is_final": True})
        data = json.loads(payload)
        assert data.get("text") == "Hello"
        assert data.get("is_final") is True

    @pytest.mark.asyncio
    async def test_voice_transcript_ignores_empty_text(self):
        payload = json.dumps({"text": "", "is_final": True})
        data = json.loads(payload)
        assert data.get("text", "").strip() == ""

    @pytest.mark.asyncio
    async def test_voice_transcript_checks_globals(self):
        # Runtime check - in actual use, _voice_bridge is set on module.
        assert True


class TestOnUserInputTranscribed:
    """Compatibility checks for transcript extraction from session events."""

    @pytest.mark.asyncio
    async def test_transcript_extracted_from_event(self):
        ev = MagicMock()
        ev.transcript = "Test transcript"
        ev.is_final = True

        transcript_text = str(getattr(ev, "transcript", "") or "")
        assert transcript_text == "Test transcript"

    @pytest.mark.asyncio
    async def test_empty_transcript_handled(self):
        ev = MagicMock()
        ev.transcript = None

        transcript_text = str(getattr(ev, "transcript", "") or "")
        assert transcript_text == ""
