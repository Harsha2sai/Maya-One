"""
Providers Package
Centralizes all provider factories for LLM, STT, and TTS
"""

from .provider_types import (
    LLMProvider,
    STTProvider,
    TTSProvider,
    LLM_DEFAULTS,
    STT_DEFAULTS,
    TTS_DEFAULTS,
)
from .llmprovider import get_llm_provider, get_llm_instance, list_llm_providers
from .sttprovider import get_stt_provider, list_stt_providers
from .ttsprovider import get_tts_provider, list_tts_providers
from .factory import ProviderFactory

__all__ = [
    # Enums
    "LLMProvider",
    "STTProvider",
    "TTSProvider",
    # Defaults
    "LLM_DEFAULTS",
    "STT_DEFAULTS",
    "TTS_DEFAULTS",
    # Factory functions
    "get_llm_provider",
    "get_llm_instance",
    "get_stt_provider",
    "get_tts_provider",
    "ProviderFactory",
    # Info functions
    "list_llm_providers",
    "list_stt_providers",
    "list_tts_providers",
]
