"""
LLM Provider Module (Backward Compatibility Layer)

This module maintains backward compatibility with existing code
while delegating to the new providers package.

MIGRATION NOTE:
This file is kept for backward compatibility. For new code, use:

    from providers import get_llm_provider, get_llm_instance
    from providers import get_stt_provider, get_tts_provider

Example:
    # Old way (still works)
    from llm_provider import get_llm_instance
    llm = get_llm_instance()
    
    # New way (recommended)
    from providers import get_llm_provider
    llm = get_llm_provider("groq", model="llama3-70b-8192")
"""

import warnings
import logging

logger = logging.getLogger(__name__)

# Import from the new providers package
try:
    from providers.llmprovider import (
        get_llm_provider,
        get_llm_instance,
        list_llm_providers,
        PROVIDER_INFO,
        _validate_api_key,
        _get_openai_llm,
        _get_groq_llm,
        _get_gemini_llm,
        _get_deepseek_llm,
        _get_qwen_llm,
        _get_anthropic_llm,
        _get_azure_openai_llm,
        _get_bedrock_llm,
        _get_together_llm,
        _get_mistral_llm,
        _get_perplexity_llm,
        _get_ollama_llm,
        _get_vllm_llm,
    )
    
    logger.info("✅ Using new providers package")
    
except ImportError as e:
    # Fallback to legacy implementation if providers package not available
    logger.warning(f"⚠️ Could not import from providers package: {e}")
    logger.warning("⚠️ Falling back to legacy implementation")
    
    import os
    import threading
    from typing import Any, Optional
    
    _llm_cache: Optional[Any] = None
    _cache_key: Optional[str] = None
    _cache_lock = threading.Lock()
    
    def get_llm_instance():
        """Legacy fallback implementation"""
        global _llm_cache, _cache_key
        
        provider = os.getenv("LLM_PROVIDER", "groq").lower()
        model = os.getenv("LLM_MODEL", "")
        current_key = f"{provider}:{model}"
        
        with _cache_lock:
            if _llm_cache is not None and _cache_key == current_key:
                return _llm_cache
        
        logger.info(f"🤖 Initializing LLM provider: {provider}")
        
        try:
            if provider == "gemini":
                llm = _get_gemini_llm_legacy(model)
            elif provider == "openai":
                llm = _get_openai_llm_legacy(model)
            elif provider == "groq":
                llm = _get_groq_llm_legacy(model)
            else:
                logger.warning(f"Unknown provider '{provider}', falling back to Groq")
                llm = _get_groq_llm_legacy(model)
            
            with _cache_lock:
                _llm_cache = llm
                _cache_key = current_key
            return llm
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize {provider}: {e}")
            llm = _get_groq_llm_legacy(model or "llama-3.1-8b-instant")
            with _cache_lock:
                _llm_cache = llm
                _cache_key = f"groq:{model or 'llama-3.1-8b-instant'}"
            return llm
    
    def _get_gemini_llm_legacy(model: str = ""):
        from livekit.plugins import google
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found")
        return google.LLM(model=model or "gemini-2.0-flash-exp", api_key=api_key)
    
    def _get_openai_llm_legacy(model: str = ""):
        from livekit.plugins import openai
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")
        return openai.LLM(model=model or "gpt-4o", api_key=api_key)
    
    def _get_groq_llm_legacy(model: str = ""):
        from livekit.plugins import groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found")
        return groq.LLM(model=model or "llama-3.1-8b-instant")
    
    def get_llm_provider(provider_name: str, model: str = "", **kwargs):
        """Simplified fallback for get_llm_provider"""
        os.environ["LLM_PROVIDER"] = provider_name
        if model:
            os.environ["LLM_MODEL"] = model
        return get_llm_instance()
    
    def list_llm_providers():
        print("Available providers: openai, groq, gemini")
    
    PROVIDER_INFO = {
        "openai": {"name": "OpenAI", "default_model": "gpt-4o"},
        "groq": {"name": "Groq", "default_model": "llama-3.1-8b-instant"},
        "gemini": {"name": "Gemini", "default_model": "gemini-2.0-flash-exp"},
    }


# Re-export for backward compatibility
__all__ = [
    "get_llm_provider",
    "get_llm_instance",
    "list_llm_providers",
    "PROVIDER_INFO",
]


def list_available_providers():
    """Backward compatible alias for list_llm_providers"""
    warnings.warn(
        "list_available_providers() is deprecated, use list_llm_providers() instead",
        DeprecationWarning,
        stacklevel=2
    )
    list_llm_providers()


if __name__ == "__main__":
    list_llm_providers()
