import asyncio
import logging
from typing import Optional, Callable, Any, Dict
from livekit.agents import tts, utils
from .provider_supervisor import ProviderSupervisor

logger = logging.getLogger(__name__)

class SilentChunkedStream(tts.ChunkedStream):
    """A TTS chunked stream that emits silent audio frames."""
    def __init__(self, *, tts: tts.TTS, input_text: str, conn_options: Any = None):
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        # Initialize with dummy PCM data info
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=self.tts.sample_rate,
            num_channels=self.tts.num_channels,
            mime_type="audio/l16", # PCM
        )
        
        # Push 100ms of silence
        silence_size = int(self.tts.sample_rate * self.tts.num_channels * 0.1 * 2) # 100ms, 16-bit
        output_emitter.push(b"\x00" * silence_size)
        output_emitter.flush()

class SilentSynthesizeStream(tts.SynthesizeStream):
    """A TTS synthesis stream that handles input but emits silence."""
    def __init__(self, *, tts: tts.TTS, conn_options: Any = None):
        super().__init__(tts=tts, conn_options=conn_options)

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=self.tts.sample_rate,
            num_channels=self.tts.num_channels,
            mime_type="audio/l16",
        )
        
        async for segment in self._input_ch:
            if not isinstance(segment, self._FlushSentinel):
                # For every text segment, push a bit of silence
                silence_size = int(self.tts.sample_rate * self.tts.num_channels * 0.05 * 2) # 50ms
                output_emitter.push(b"\x00" * silence_size)
                output_emitter.flush()

class ResilientTTSProxy(tts.TTS):
    """
    Resilient TTS Proxy that wraps a real TTS provider and ensures
    audio streams never break by providing silent fallbacks.
    """
    def __init__(
        self, 
        provider: tts.TTS, 
        supervisor: ProviderSupervisor,
        factory_fn: Callable[[], Any]
    ):
        super().__init__(
            capabilities=provider.capabilities,
            sample_rate=provider.sample_rate,
            num_channels=provider.num_channels,
        )
        self._provider = provider
        self._supervisor = supervisor
        self._factory_fn = factory_fn
        self._name = "tts"
        
        # Register with supervisor
        self._supervisor.register_provider(self._name, self)

    @property
    def capabilities(self) -> tts.TTSCapabilities:
        return self._provider.capabilities

    def synthesize(self, text: str, **kwargs) -> tts.ChunkedStream:
        try:
            stream = self._provider.synthesize(text, **kwargs)
            self._supervisor.mark_healthy(self._name)
            return stream
        except Exception as e:
            logger.error(f"TTS.synthesize failed for {self._name}: {e}")
            self._supervisor.mark_failed(self._name, e)
            return SilentChunkedStream(tts=self, input_text=text, conn_options=kwargs.get("conn_options"))

    def stream(self, **kwargs) -> tts.SynthesizeStream:
        try:
            stream = self._provider.stream(**kwargs)
            self._supervisor.mark_healthy(self._name)
            return stream
        except Exception as e:
            logger.error(f"TTS.stream failed for {self._name}: {e}")
            self._supervisor.mark_failed(self._name, e)
            return SilentSynthesizeStream(tts=self, conn_options=kwargs.get("conn_options"))

    def replace_provider(self, new_provider: tts.TTS):
        """Inject a new provider instance (hot-swap)."""
        logger.info(f"Hot-swapping TTS provider: {type(new_provider).__name__}")
        self._provider = new_provider
        self._sample_rate = new_provider.sample_rate
        self._num_channels = new_provider.num_channels

    async def attempt_reconnect(self) -> bool:
        """Attempt to recreate the provider via factory function."""
        try:
            logger.info(f"Attempting TTS reconnection for {self._name}...")
            new_provider = await asyncio.to_thread(self._factory_fn)
            self.replace_provider(new_provider)
            return True
        except Exception as e:
            logger.error(f"TTS reconnection attempt failed: {e}")
            return False

    def __getattr__(self, name):
        """Forward any other calls to the underlying provider."""
        return getattr(self._provider, name)
