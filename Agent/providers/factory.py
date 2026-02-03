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
    def get_stt(provider_name: str, language: str, model: str) -> Any:
        """Initialize STT with fallback to Groq"""
        try:
            instance = get_stt_provider(
                provider_name=provider_name,
                language=language,
                model=model,
            )
            logger.info(f"✅ STT initialized: {provider_name}")
            return instance
        except Exception as e:
            logger.error(f"❌ Failed to initialize STT provider {provider_name}: {e}")
            # Fallback to Groq STT
            from livekit.plugins import groq
            logger.warning("⚠️ Falling back to Groq STT (whisper-large-v3-turbo, en)")
            return groq.STT(model="whisper-large-v3-turbo", language="en")

    @staticmethod
    def get_tts(provider_name: str, voice: str, model: str) -> Any:
        """Initialize TTS with fallback to OpenAI"""
        try:
            instance = get_tts_provider(
                provider_name=provider_name,
                voice=voice,
                model=model,
            )
            logger.info(f"✅ TTS initialized: {provider_name}")
            return instance
        except Exception as e:
            logger.error(f"❌ Failed to initialize TTS provider {provider_name}: {e}")
            # Fallback to OpenAI TTS
            from livekit.plugins import openai
            logger.warning("⚠️ Falling back to OpenAI TTS (tts-1, alloy)")
            return openai.TTS(model="tts-1", voice="alloy")
