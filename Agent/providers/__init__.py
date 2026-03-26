"""
Providers Package
Centralizes all provider factories for LLM, STT, and TTS
"""

print("🔍 DEBUG: providers/__init__ - Importing provider_types...")
from .provider_types import (
    LLMProvider,
    STTProvider,
    TTSProvider,
    LLM_DEFAULTS,
    STT_DEFAULTS,
    TTS_DEFAULTS,
)
print("🔍 DEBUG: providers/__init__ - Importing llmprovider...")
from .llmprovider import get_llm_provider, get_llm_instance, list_llm_providers
print("🔍 DEBUG: providers/__init__ - Importing sttprovider...")
from .sttprovider import get_stt_provider, list_stt_providers
print("🔍 DEBUG: providers/__init__ - Importing ttsprovider...")
from .ttsprovider import get_tts_provider, list_tts_providers
print("🔍 DEBUG: providers/__init__ - Importing factory...")
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

# Singleton Cache Patch for Factory
# We patch the Factory class methods to use a cache
_provider_cache = {}

original_get_llm_provider = get_llm_provider
def cached_get_llm_provider(*args, **kwargs):
    key = f"llm_{args}_{kwargs}"
    if key not in _provider_cache:
        _provider_cache[key] = original_get_llm_provider(*args, **kwargs)
    return _provider_cache[key]

# We need to apply this to the actual imported functions if we want it to work transparently.
# A better way is to modify the ProviderFactory class in 'factory.py' if possible.
# But since I only see __init__.py here, let's assume the user wants me to modify THIS file or 'factory.py'.
# The previous valid 'view_file' on providers/__init__.py showed imports from .factory. 
# I should modify .factory instead.

