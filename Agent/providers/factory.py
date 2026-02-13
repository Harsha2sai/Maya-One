import logging
import os
from typing import Any, Optional
from .llmprovider import get_llm_provider
from .sttprovider import get_stt_provider
from .ttsprovider import get_tts_provider
from config.settings import settings

logger = logging.getLogger(__name__)

class ProviderFactory:
    """
    Factory for resolving and initializing STT, LLM, and TTS providers.
    Encapsulates fallback logic and logging to keep the main agent script clean.
    """

    @staticmethod
    def get_llm(provider_name: str, model: str, temperature: Optional[float] = None) -> Any:
        """Initialize LLM with fallback to Groq"""
        try:
            temp = temperature if temperature is not None else settings.llm_temperature
            instance = get_llm_provider(
                provider_name=provider_name,
                model=model,
                temperature=temp,
            )
            logger.info(f"✅ LLM initialized: {provider_name}")
            return instance
        except Exception as e:
            logger.error(f"❌ Failed to initialize LLM provider {provider_name}: {e}")
            # Fallback to Groq LLM
            from livekit.plugins import groq
            logger.warning("⚠️ Falling back to Groq LLM (llama-3.1-8b-instant)")
            return groq.LLM(model="llama-3.1-8b-instant")

    @staticmethod
    def get_stt(provider_name: str, language: str, model: str, supervisor: Optional[Any] = None) -> Any:
        """Initialize STT with fallback to Groq and optional resiliency"""
        try:
            instance = get_stt_provider(
                provider_name=provider_name,
                language=language,
                model=model,
            )
            logger.info(f"✅ STT initialized: {provider_name}")
            
            if supervisor:
                from core.providers.resilient_stt import ResilientSTTProxy
                return ResilientSTTProxy(
                    provider=instance,
                    supervisor=supervisor,
                    factory_fn=lambda: ProviderFactory.get_stt(provider_name, language, model)
                )
            return instance
        except Exception as e:
            logger.error(f"❌ Failed to initialize STT provider {provider_name}: {e}")
            # Fallback to Groq STT
            from livekit.plugins import groq
            logger.warning("⚠️ Falling back to Groq STT (whisper-large-v3-turbo, en)")
            return groq.STT(model="whisper-large-v3-turbo", language="en")

    @staticmethod
    def get_tts(provider_name: str, voice: str, model: str, supervisor: Optional[Any] = None) -> Any:
        """Initialize TTS with fallback to OpenAI and optional resiliency"""
        try:
            instance = get_tts_provider(
                provider_name=provider_name,
                voice=voice,
                model=model,
            )
            logger.info(f"✅ TTS initialized: {provider_name}")
            
            if supervisor:
                from core.providers.resilient_tts import ResilientTTSProxy
                return ResilientTTSProxy(
                    provider=instance,
                    supervisor=supervisor,
                    factory_fn=lambda: ProviderFactory.get_tts(provider_name, voice, model)
                )
            return instance
        except Exception as e:
            logger.error(f"❌ Failed to initialize TTS provider {provider_name}: {e}")
            # Fallback to Edge TTS (Free)
            try:
                logger.warning("⚠️ Falling back to Edge TTS (en-US-JennyNeural)")
                return get_tts_provider(provider_name="edge_tts", voice="en-US-JennyNeural")
            except Exception as fe:
                logger.error(f"❌ Primary fallback (Edge TTS) failed: {fe}. Using OpenAI as last resort.")
                from livekit.plugins import openai
                return openai.TTS(model="tts-1", voice="alloy")
