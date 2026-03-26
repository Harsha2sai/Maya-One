import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from livekit.agents import stt, tts
from core.providers.provider_health import ProviderState
from core.providers.provider_supervisor import ProviderSupervisor
from core.providers.resilient_stt import ResilientSTTProxy
from core.providers.resilient_tts import ResilientTTSProxy
from providers.factory import ProviderFactory
from providers import factory as provider_factory_module

@pytest.mark.anyio
async def test_supervisor_state_transitions():
    supervisor = ProviderSupervisor()
    supervisor.register_provider("test", MagicMock())
    
    health = supervisor.get_health("test")
    assert health.state == ProviderState.HEALTHY
    
    # 1 failure -> DEGRADED
    supervisor.mark_failed("test", Exception("error 1"))
    assert health.state == ProviderState.DEGRADED
    
    # 4 failures -> OFFLINE
    supervisor.mark_failed("test", Exception("error 2"))
    supervisor.mark_failed("test", Exception("error 3"))
    supervisor.mark_failed("test", Exception("error 4"))
    assert health.state == ProviderState.OFFLINE
    
    # mark healthy -> HEALTHY
    supervisor.mark_healthy("test")
    assert health.state == ProviderState.HEALTHY
    assert health.failure_count == 0

@pytest.mark.anyio
async def test_stt_proxy_fallback():
    mock_stt = MagicMock(spec=stt.STT)
    mock_stt.provider = "stt"
    mock_stt.capabilities = stt.STTCapabilities(streaming=True, interim_results=True)
    mock_stt.stream.side_effect = Exception("STT Down")
    
    supervisor = ProviderSupervisor()
    proxy = ResilientSTTProxy(mock_stt, supervisor, lambda: mock_stt)
    
    # Calling stream should not raise, but return EmptyTranscriptStream
    stream = proxy.stream()
    assert isinstance(stream, stt.SpeechStream)
    
    health = supervisor.get_health("stt")
    assert health.state == ProviderState.DEGRADED

@pytest.mark.anyio
async def test_tts_proxy_fallback():
    mock_tts = MagicMock(spec=tts.TTS)
    mock_tts.provider = "tts"
    mock_tts.capabilities = tts.TTSCapabilities(streaming=True)
    mock_tts.sample_rate = 24000
    mock_tts.num_channels = 1
    mock_tts.synthesize.side_effect = Exception("TTS Down")
    
    supervisor = ProviderSupervisor()
    proxy = ResilientTTSProxy(mock_tts, supervisor, lambda: mock_tts)
    
    # Calling synthesize should not raise, but return SilentChunkedStream
    stream = proxy.synthesize("hello")
    assert isinstance(stream, tts.ChunkedStream)
    
    health = supervisor.get_health("tts")
    assert health.state == ProviderState.DEGRADED

@pytest.mark.anyio
async def test_hot_swap():
    mock_v1 = MagicMock(spec=stt.STT)
    mock_v1.provider = "stt"
    mock_v1.capabilities = stt.STTCapabilities(streaming=True, interim_results=True)
    mock_v2 = MagicMock(spec=stt.STT)
    mock_v2.provider = "stt"
    mock_v2.capabilities = stt.STTCapabilities(streaming=True, interim_results=True)
    
    supervisor = ProviderSupervisor()
    proxy = ResilientSTTProxy(mock_v1, supervisor, lambda: mock_v1)
    
    proxy.replace_provider(mock_v2)
    proxy.stream()
    
    mock_v1.stream.assert_not_called()
    mock_v2.stream.assert_called_once()
    assert proxy.capabilities == mock_v2.capabilities

@pytest.mark.anyio
async def test_reconnect_logic():
    mock_v1 = MagicMock(spec=stt.STT)
    mock_v1.provider = "stt"
    mock_v1.capabilities = stt.STTCapabilities(streaming=True, interim_results=True)
    mock_v1.stream.side_effect = Exception("Down")

    mock_v2 = MagicMock(spec=stt.STT)
    mock_v2.provider = "stt"
    mock_v2.capabilities = stt.STTCapabilities(streaming=True, interim_results=True)
    
    factory_mock = MagicMock(return_value=mock_v2)
    
    supervisor = ProviderSupervisor()
    proxy = ResilientSTTProxy(mock_v1, supervisor, factory_mock)
    
    # Trigger offline state
    for _ in range(4):
        proxy.stream()
    
    assert supervisor.get_health("stt").state == ProviderState.OFFLINE
    
    # Attempt reconnect using the REAL method (not overwritten)
    # But factory_mock needs to be wrapped in a way that it can be called in a thread
    # or just made to work. factory_mock is already sync.
    
    result = await proxy.attempt_reconnect()
    assert result is True
    factory_mock.assert_called_once()
    
    # Verify proxy now uses mock_v2
    proxy.stream()
    mock_v2.stream.assert_called_once()


def test_llm_circuit_opens_after_failures():
    supervisor = ProviderSupervisor(failure_threshold=3)
    supervisor.register_provider("api.groq.com", MagicMock())

    for _ in range(3):
        supervisor.record_failure("api.groq.com")

    assert supervisor.is_open("api.groq.com")


@pytest.mark.anyio
async def test_circuit_recovers_after_window():
    supervisor = ProviderSupervisor(failure_threshold=3, recovery_timeout_s=0.1)
    supervisor.register_provider("api.groq.com", MagicMock())

    for _ in range(3):
        supervisor.record_failure("api.groq.com")

    assert supervisor.is_open("api.groq.com")
    await asyncio.sleep(0.2)
    assert supervisor.should_allow_request("api.groq.com")
    supervisor.record_success("api.groq.com")
    supervisor.record_success("api.groq.com")
    assert not supervisor.is_open("api.groq.com")


def test_tts_fallback_when_elevenlabs_open(monkeypatch, caplog):
    class FakeTTS:
        provider = "edge_tts"
        capabilities = tts.TTSCapabilities(streaming=True)
        sample_rate = 24000
        num_channels = 1

        def synthesize(self, text, **kwargs):
            return MagicMock(spec=tts.ChunkedStream)

    supervisor = ProviderSupervisor()
    supervisor.register_provider("api.elevenlabs.io", MagicMock())
    for _ in range(supervisor.failure_threshold + 1):
        supervisor.record_failure("api.elevenlabs.io")

    calls = []

    def fake_get_tts_provider(provider_name, voice="", model="", **kwargs):
        calls.append(provider_name)
        if provider_name == "cartesia":
            raise RuntimeError("cartesia unavailable")
        return FakeTTS()

    monkeypatch.setattr(provider_factory_module, "get_tts_provider", fake_get_tts_provider)
    ProviderFactory.reset_cache()

    result = ProviderFactory.get_tts("elevenlabs", "", "", supervisor=supervisor)

    assert isinstance(result, ResilientTTSProxy)
    assert calls == ["cartesia", "edge_tts"]
    assert "edge_tts_promoted_to_primary" in caplog.text


def test_stt_fails_over_to_groq_when_deepgram_open(monkeypatch):
    class FakeSTT:
        provider = "groq"
        capabilities = stt.STTCapabilities(streaming=True, interim_results=True)

        def stream(self, **kwargs):
            return MagicMock(spec=stt.SpeechStream)

    supervisor = ProviderSupervisor()
    supervisor.register_provider("api.deepgram.com", MagicMock())
    for _ in range(supervisor.failure_threshold + 1):
        supervisor.record_failure("api.deepgram.com")

    calls = []

    def fake_get_stt_provider(provider_name, language="en", model="", **kwargs):
        calls.append(provider_name)
        return FakeSTT()

    monkeypatch.setattr(provider_factory_module, "get_stt_provider", fake_get_stt_provider)
    ProviderFactory.reset_cache()

    result = ProviderFactory.get_stt("deepgram", "en", "nova-2", supervisor=supervisor)

    assert isinstance(result, ResilientSTTProxy)
    assert calls[0] == "groq"


def test_system_returns_to_primary_after_outage_window(monkeypatch):
    class FakeTTS:
        provider = "elevenlabs"
        capabilities = tts.TTSCapabilities(streaming=True)
        sample_rate = 24000
        num_channels = 1

        def synthesize(self, text, **kwargs):
            return MagicMock(spec=tts.ChunkedStream)

    supervisor = ProviderSupervisor(failure_threshold=2, recovery_timeout_s=0.05)
    supervisor.register_provider("api.elevenlabs.io", MagicMock())
    supervisor.record_failure("api.elevenlabs.io")
    supervisor.record_failure("api.elevenlabs.io")
    assert supervisor.is_open("api.elevenlabs.io")
    time = __import__("time")
    time.sleep(0.06)
    assert supervisor.should_allow_request("api.elevenlabs.io")
    supervisor.record_success("api.elevenlabs.io")
    supervisor.record_success("api.elevenlabs.io")
    assert not supervisor.is_open("api.elevenlabs.io")

    calls = []

    def fake_get_tts_provider(provider_name, voice="", model="", **kwargs):
        calls.append(provider_name)
        return FakeTTS()

    monkeypatch.setattr(provider_factory_module, "get_tts_provider", fake_get_tts_provider)
    ProviderFactory.reset_cache()
    result = ProviderFactory.get_tts("elevenlabs", "", "", supervisor=supervisor)

    assert isinstance(result, ResilientTTSProxy)
    assert calls[0] == "elevenlabs"
