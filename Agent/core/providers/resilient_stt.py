import asyncio
import logging
from typing import AsyncIterable, Optional, Callable, Dict, Any
from livekit.agents import stt
from livekit.rtc import AudioFrame
from .provider_supervisor import ProviderSupervisor

logger = logging.getLogger(__name__)

class EmptyTranscriptStream(stt.SpeechStream):
    """A transcript stream that emits nothing but stays alive."""
    def __init__(self, *, stt: stt.STT, conn_options: Any = None):
        super().__init__(stt=stt, conn_options=conn_options)

    async def _run(self):
        # Simply wait forever (or until cancelled) without emitting any events
        while True:
            await asyncio.sleep(3600)

    def push_audio(self, frame):
        # Dropping audio frames as we're in offline/silent mode
        pass

    def end_input(self):
        # Gracefully handle end of input
        pass

class ResilientSTTProxy(stt.STT):
    """
    Resilient STT Proxy that wraps a real STT provider and prevents
    fatal errors from propagating upward.
    """
    def __init__(
        self, 
        provider: stt.STT, 
        supervisor: ProviderSupervisor,
        factory_fn: Callable[[], Any]
    ):
        super().__init__(
            capabilities=provider.capabilities
        )
        self._provider = provider
        self._supervisor = supervisor
        self._factory_fn = factory_fn
        self._name = "stt"
        
        # Register with supervisor
        self._supervisor.register_provider(self._name, self)

    @property
    def capabilities(self) -> stt.STTCapabilities:
        return self._provider.capabilities

    def stream(self, **kwargs) -> stt.SpeechStream:
        try:
            stream = self._provider.stream(**kwargs)
            self._supervisor.mark_healthy(self._name)
            return stream
        except Exception as e:
            logger.error(f"STT.stream failed for {self._name}: {e}")
            self._supervisor.mark_failed(self._name, e)
            return EmptyTranscriptStream(stt=self, conn_options=kwargs.get("conn_options"))

    async def _recognize_impl(
        self, 
        buffer: AudioFrame | AsyncIterable[AudioFrame], 
        *, 
        language: Optional[str] = None
    ) -> stt.SpeechEvent:
        try:
            # Note: _recognize_impl is the internal method LiveKit STT calls
            if hasattr(self._provider, '_recognize_impl'):
                result = await self._provider._recognize_impl(buffer, language=language)
            else:
                result = await self._provider.recognize(buffer, language=language)
            
            self._supervisor.mark_healthy(self._name)
            return result
        except Exception as e:
            logger.error(f"STT._recognize_impl failed for {self._name}: {e}")
            self._supervisor.mark_failed(self._name, e)
            # Return empty result to avoid crash
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[]
            )

    async def recognize(self, buffer: AudioFrame | AsyncIterable[AudioFrame], *, language: Optional[str] = None):
        return await self._recognize_impl(buffer, language=language)

    def replace_provider(self, new_provider: stt.STT):
        """Inject a new provider instance (hot-swap)."""
        logger.info(f"Hot-swapping STT provider: {type(new_provider).__name__}")
        self._provider = new_provider

    async def attempt_reconnect(self) -> bool:
        """Attempt to recreate the provider via factory function."""
        try:
            logger.info(f"Attempting STT reconnection for {self._name}...")
            new_provider = await asyncio.to_thread(self._factory_fn)
            self.replace_provider(new_provider)
            return True
        except Exception as e:
            logger.error(f"STT reconnection attempt failed: {e}")
            return False

    def __getattr__(self, name):
        """Forward any other calls to the underlying provider."""
        return getattr(self._provider, name)
