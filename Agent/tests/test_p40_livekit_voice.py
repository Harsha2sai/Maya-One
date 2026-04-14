"""Tests for LiveKit voice project bridge behavior (P40)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.livekit import VoiceProjectBridge


class MockProjectOrchestrator:
    """Project mode mock that mirrors current ProjectModeOrchestrator API."""

    def __init__(self):
        self._active = None
        self.requirements = []
        self.advance_calls = 0
        self.cancel_calls = 0

    def is_active(self):
        return self._active is not None

    async def start(self, project_name: str, description: str = ""):
        self._active = SimpleNamespace(name=project_name, description=description, prd=None)
        self.requirements = []
        return f"Project '{project_name}' started."

    async def add_requirement(self, requirement: str):
        if not self._active:
            return "No active project. Use /project start <name>."
        self.requirements.append(requirement)
        return f"Requirement {len(self.requirements)} recorded. Add more or say 'done'."

    async def advance(self):
        self.advance_calls += 1
        return "Advanced project phase."

    async def status(self):
        if not self._active:
            return "No active project."
        return f"Project: {self._active.name}"

    async def cancel(self):
        if not self._active:
            return "No active project to cancel."
        name = self._active.name
        self._active = None
        self.cancel_calls += 1
        return f"Project '{name}' cancelled."


class MockBuddy:
    """Mock buddy for bridge constructor compatibility."""


@pytest.mark.asyncio
async def test_voice_bridge_ignores_non_project_when_inactive():
    bridge = VoiceProjectBridge(MockProjectOrchestrator(), MockBuddy())
    response = await bridge.on_transcript("what's the weather", is_final=True)
    assert response is None
    assert bridge.is_active is False


@pytest.mark.asyncio
async def test_voice_bridge_starts_project_from_voice_alias():
    orchestrator = MockProjectOrchestrator()
    bridge = VoiceProjectBridge(orchestrator, MockBuddy())
    response = await bridge.on_transcript("start project Voice Demo", is_final=True)
    assert "started" in response.lower()
    assert bridge.is_active is True


@pytest.mark.asyncio
async def test_voice_bridge_routes_active_text_as_requirement():
    orchestrator = MockProjectOrchestrator()
    bridge = VoiceProjectBridge(orchestrator, MockBuddy())
    await bridge.on_transcript("project start Website", is_final=True)
    response = await bridge.on_transcript("Use React and FastAPI", is_final=True)
    assert "requirement 1" in response.lower()
    assert orchestrator.requirements == ["Use React and FastAPI"]


@pytest.mark.asyncio
async def test_voice_bridge_maps_done_to_next_when_active():
    orchestrator = MockProjectOrchestrator()
    bridge = VoiceProjectBridge(orchestrator, MockBuddy())
    await bridge.on_transcript("project start Website", is_final=True)
    response = await bridge.on_transcript("done", is_final=True)
    assert response == "Advanced project phase."
    assert orchestrator.advance_calls == 1


@pytest.mark.asyncio
async def test_voice_bridge_get_prd_returns_none_when_missing():
    bridge = VoiceProjectBridge(MockProjectOrchestrator(), MockBuddy())
    assert await bridge.get_prd() is None


@pytest.mark.asyncio
async def test_voice_bridge_get_prd_returns_text_when_available():
    orchestrator = MockProjectOrchestrator()
    bridge = VoiceProjectBridge(orchestrator, MockBuddy())
    await bridge.on_transcript("project start Website", is_final=True)
    orchestrator._active.prd = "PRD body"
    assert await bridge.get_prd() == "PRD body"


@pytest.mark.asyncio
async def test_voice_bridge_end_session_cancels_active_project():
    orchestrator = MockProjectOrchestrator()
    bridge = VoiceProjectBridge(orchestrator, MockBuddy())
    await bridge.on_transcript("project start Website", is_final=True)
    response = await bridge.end_session()
    assert "cancelled" in response.lower()
    assert bridge.is_active is False
    assert orchestrator.cancel_calls == 1


@pytest.mark.asyncio
async def test_voice_bridge_end_session_returns_none_when_inactive():
    bridge = VoiceProjectBridge(MockProjectOrchestrator(), MockBuddy())
    assert await bridge.end_session() is None
