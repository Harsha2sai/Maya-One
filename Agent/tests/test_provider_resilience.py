import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from livekit.agents import stt, tts
from core.providers.provider_health import ProviderState
from core.providers.provider_supervisor import ProviderSupervisor
from core.providers.resilient_stt import ResilientSTTProxy
from core.providers.resilient_tts import ResilientTTSProxy

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
    mock_v1.capabilities = stt.STTCapabilities(streaming=True, interim_results=True)
    mock_v2 = MagicMock(spec=stt.STT)
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
    mock_v1.capabilities = stt.STTCapabilities(streaming=True, interim_results=True)
    mock_v1.stream.side_effect = Exception("Down")
    
    mock_v2 = MagicMock(spec=stt.STT)
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
