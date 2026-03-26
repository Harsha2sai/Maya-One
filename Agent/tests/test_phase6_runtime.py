import logging
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

import agent
from core.runtime.lifecycle import MayaRuntimeMode, RuntimeLifecycleManager


def test_turn_detection_active_eou_or_fallback_logged(monkeypatch, caplog):
    monkeypatch.setenv("VOICE_TURN_DETECTION_MODE", "eou_multilingual")
    monkeypatch.setenv("VOICE_TURN_DETECTION_FALLBACK", "stt")
    monkeypatch.setattr("huggingface_hub.hf_hub_download", lambda **_kwargs: "/tmp/model")

    from livekit.plugins.turn_detector import multilingual

    class DummyModel:
        pass

    monkeypatch.setattr(multilingual, "MultilingualModel", DummyModel)

    with caplog.at_level(logging.INFO):
        detector, mode, fallback_reason = agent._build_turn_detection()

    assert isinstance(detector, DummyModel)
    assert mode == "eou_multilingual"
    assert fallback_reason is None
    assert "turn_detection_active=eou_multilingual" in caplog.text


def test_turn_detection_fallback_to_stt_on_model_load_failure(monkeypatch, caplog):
    monkeypatch.setenv("VOICE_TURN_DETECTION_MODE", "eou_multilingual")
    monkeypatch.setenv("VOICE_TURN_DETECTION_FALLBACK", "stt")
    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        Mock(side_effect=RuntimeError("missing model assets")),
    )

    with caplog.at_level(logging.WARNING):
        detector, mode, fallback_reason = agent._build_turn_detection()

    assert detector == "stt"
    assert mode == "stt"
    assert fallback_reason and fallback_reason.startswith("eou_multilingual_load_failed")
    assert "turn_detection_active=stt" in caplog.text


def test_endpointing_delay_defaults(monkeypatch):
    monkeypatch.delenv("MIN_ENDPOINTING_DELAY", raising=False)
    monkeypatch.delenv("MAX_ENDPOINTING_DELAY", raising=False)
    monkeypatch.delenv("VOICE_MIN_ENDPOINTING_DELAY_S", raising=False)
    monkeypatch.delenv("VOICE_MAX_ENDPOINTING_DELAY_S", raising=False)
    min_delay, max_delay = agent._resolve_endpointing_delays()
    assert min_delay == pytest.approx(1.5)
    assert max_delay == pytest.approx(4.0)


def test_endpointing_delay_env_override_and_clamp(monkeypatch):
    monkeypatch.setenv("MIN_ENDPOINTING_DELAY", "1.5")
    monkeypatch.setenv("MAX_ENDPOINTING_DELAY", "1.0")
    monkeypatch.setenv("VOICE_MIN_ENDPOINTING_DELAY_S", "1.5")
    monkeypatch.setenv("VOICE_MAX_ENDPOINTING_DELAY_S", "3.0")
    min_delay, max_delay = agent._resolve_endpointing_delays()
    assert min_delay == pytest.approx(1.5)
    assert max_delay == pytest.approx(1.5)


def test_endpointing_delay_legacy_env_compatibility(monkeypatch):
    monkeypatch.delenv("MIN_ENDPOINTING_DELAY", raising=False)
    monkeypatch.delenv("MAX_ENDPOINTING_DELAY", raising=False)
    monkeypatch.setenv("VOICE_MIN_ENDPOINTING_DELAY_S", "1.4")
    monkeypatch.setenv("VOICE_MAX_ENDPOINTING_DELAY_S", "2.8")
    min_delay, max_delay = agent._resolve_endpointing_delays()
    assert min_delay == pytest.approx(1.4)
    assert max_delay == pytest.approx(2.8)


@pytest.mark.asyncio
async def test_memory_ingestor_started_in_worker_mode(monkeypatch):
    lifecycle = RuntimeLifecycleManager(MayaRuntimeMode.WORKER)

    class DummyIngestor:
        def __init__(self) -> None:
            self.index_existing_files = Mock()
            self.start = AsyncMock()

    dummy_ingestor = DummyIngestor()

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("core.runtime.lifecycle.asyncio.to_thread", _to_thread)
    monkeypatch.setattr(
        "core.runtime.lifecycle.GlobalAgentContainer.memory_ingestor",
        dummy_ingestor,
        raising=False,
    )

    await lifecycle._start_memory_ingestor_task()

    dummy_ingestor.index_existing_files.assert_called_once()
    dummy_ingestor.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_ingestor_started_in_console_mode(monkeypatch):
    lifecycle = RuntimeLifecycleManager(MayaRuntimeMode.CONSOLE)
    lifecycle.architecture_phase = 6
    start_ingestor = AsyncMock()
    monkeypatch.setattr(lifecycle, "_start_memory_ingestor_task", start_ingestor)
    monkeypatch.setattr(lifecycle, "_print_banner", lambda: None)
    monkeypatch.setattr("builtins.input", Mock(side_effect=EOFError))

    scheduled_tasks = []

    def _start_background_task(coro):
        task = asyncio.create_task(coro)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(lifecycle, "_start_background_task", _start_background_task)

    await lifecycle._boot_console_mode()
    if scheduled_tasks:
        await asyncio.gather(*scheduled_tasks, return_exceptions=True)

    start_ingestor.assert_awaited_once()
