import asyncio
import json
import logging
import os
import time
from typing import Optional, Dict, Any

print("🔍 DEBUG: ProviderFactory - Importing ProviderSupervisor...")
from core.providers.provider_supervisor import ProviderSupervisor
print("🔍 DEBUG: ProviderFactory - Importing provider_types...")
from .provider_types import LLMProvider, STTProvider, TTSProvider
print("🔍 DEBUG: ProviderFactory - Importing settings...")
from config.settings import settings
from .llmprovider import get_llm_provider
from .sttprovider import get_stt_provider
from .ttsprovider import get_tts_provider

logger = logging.getLogger(__name__)

_PROVIDER_HOST_MAP = {
    "groq": "api.groq.com",
    "elevenlabs": "api.elevenlabs.io",
    "deepgram": "api.deepgram.com",
    "cartesia": "api.cartesia.ai",
    "openai": "api.openai.com",
    "azure": "azure",
    "edge_tts": "edge_tts",
}

class ProviderFactory:
    """
    Factory for resolving and initializing STT, LLM, and TTS providers.
    Encapsulates fallback logic and logging to keep the main agent script clean.
    """
    
    # Singleton Cache
    _cache = {}
    DEFAULT_LLM_TIMEOUT = 30.0
    DEFAULT_STT_TIMEOUT = 15.0
    DEFAULT_TTS_TIMEOUT = 15.0
    TTS_CANDIDATE_ORDER = ["elevenlabs", "cartesia", "edge_tts"]
    _PRIMARY_TTS_PROVIDERS = tuple(TTS_CANDIDATE_ORDER[:-1])
    _EDGE_TTS_PROVIDER = "edge_tts"

    @classmethod
    def reset_cache(cls):
        """Clear the provider cache (useful for testing)"""
        cls._cache.clear()

    @staticmethod
    def _stable_kwargs(kwargs: Dict[str, Any]) -> str:
        """Serialize kwargs into a deterministic cache-key fragment."""
        if not kwargs:
            return ""
        try:
            return json.dumps(kwargs, sort_keys=True, default=str)
        except Exception:
            return str(sorted((str(k), str(v)) for k, v in kwargs.items()))

    @classmethod
    def _resolve_tts_candidates(cls, provider_name: str) -> list[str]:
        normalized = str(provider_name or "").strip().lower()
        edge_aliases = {"", "edge", "edge_tts", "edgetts", "microsoft"}
        prefer_premium_for_edge = (
            str(os.getenv("TTS_EDGE_PREFERS_PREMIUM", "false")).strip().lower()
            in {"1", "true", "yes", "on"}
        )

        if normalized in edge_aliases:
            if prefer_premium_for_edge:
                return [*cls._PRIMARY_TTS_PROVIDERS, cls._EDGE_TTS_PROVIDER]
            return [cls._EDGE_TTS_PROVIDER, *cls._PRIMARY_TTS_PROVIDERS]

        candidates: list[str] = [normalized]
        for provider in (*cls._PRIMARY_TTS_PROVIDERS, cls._EDGE_TTS_PROVIDER):
            if provider not in candidates:
                candidates.append(provider)
        return candidates

    @staticmethod
    def _provider_host(provider_name: str) -> str:
        normalized = str(provider_name or "").strip().lower()
        return _PROVIDER_HOST_MAP.get(normalized, normalized or "unknown")

    @classmethod
    def _normalize_tts_params_for_provider(
        cls,
        provider_name: str,
        voice: str,
        model: str,
    ) -> tuple[str, str]:
        provider = str(provider_name or "").strip().lower()
        normalized_voice = str(voice or "").strip()
        normalized_model = str(model or "").strip()

        # Edge-TTS only accepts Microsoft voice identifiers (typically *Neural).
        # If we receive a UUID-like premium provider voice id, drop to provider default.
        if provider == cls._EDGE_TTS_PROVIDER:
            if normalized_voice and "neural" not in normalized_voice.lower():
                normalized_voice = ""
            # Edge-TTS ignores model; avoid carrying incompatible model names.
            normalized_model = ""

        # ElevenLabs voices are ids. If an Edge-style voice name leaks in, reset to default.
        if provider == "elevenlabs" and "neural" in normalized_voice.lower():
            normalized_voice = ""

        return normalized_voice, normalized_model

    @staticmethod
    async def _with_timeout(coro, timeout: float, provider_type: str):
        """Wrapper to apply timeout to provider initialization."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"❌ {provider_type} provider initialization timeout after {timeout}s")
            raise

    @classmethod
    def get_llm(
        cls,
        provider_name: str,
        model: str,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Any:
        """Initialize LLM with fallback to Groq and connection timeout. Caches instances."""
        temp = temperature if temperature is not None else settings.llm_temperature
        kwargs_key = cls._stable_kwargs(kwargs)
        cache_key = f"llm:{provider_name}:{model}:{temp}:{kwargs_key}"
        
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        timeout = timeout or cls.DEFAULT_LLM_TIMEOUT
        try:
            instance = get_llm_provider(
                provider_name=provider_name,
                model=model,
                temperature=temp,
                **kwargs,
            )
            logger.info(f"✅ LLM initialized: {provider_name} ({model})")
            cls._cache[cache_key] = instance
            return instance
        except Exception as e:
            logger.error(f"❌ Failed to initialize LLM provider {provider_name}: {e}")
            fallback_model = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
            logger.warning(f"⚠️ Falling back to Groq LLM ({fallback_model})")
            slots = [2, 3, 1]
            last_err: Optional[Exception] = None
            for slot in slots:
                slot_key = os.getenv(f"GROQ_API_KEY_{slot}", "").strip() if slot > 1 else os.getenv("GROQ_API_KEY", "").strip()
                if not slot_key:
                    continue
                try:
                    return get_llm_provider(
                        provider_name="groq",
                        model=fallback_model,
                        temperature=temp,
                        key_slot=slot,
                    )
                except Exception as slot_err:
                    last_err = slot_err
                    logger.warning(f"⚠️ Groq fallback slot {slot} failed: {slot_err}")
            if last_err:
                raise last_err
            raise

    @classmethod
    def get_stt(cls, provider_name: str, language: str, model: str, supervisor: Optional[Any] = None, timeout: Optional[float] = None) -> Any:
        """Initialize STT with fallback to Groq, optional resiliency, and connection timeout. Caches instances."""
        # Note: Supervisor wrapping makes caching tricky if supervisor changes.
        # Assuming supervisor is persistent or we verify it. 
        # For simplicity, we cache the *core* provider if possible, but the factory returns the wrapped one.
        # If we cache the wrapped one, we assume supervisor doesn't change.
        
        cache_key = f"stt:{provider_name}:{language}:{model}:{id(supervisor) if supervisor else 'none'}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        timeout = timeout or cls.DEFAULT_STT_TIMEOUT
        requested_provider = str(provider_name or "").strip().lower()
        candidate_chain = [requested_provider]
        for fallback in ("groq", os.getenv("STT_SECONDARY_FALLBACK", "azure").strip().lower() or "azure"):
            if fallback and fallback not in candidate_chain:
                candidate_chain.append(fallback)

        last_error: Optional[Exception] = None
        for candidate in candidate_chain:
            if supervisor and supervisor.is_open(cls._provider_host(candidate)):
                logger.warning(
                    "circuit_breaker_open provider=%s failing_over_from=%s",
                    cls._provider_host(candidate),
                    candidate,
                )
                continue
            try:
                instance = get_stt_provider(
                    provider_name=candidate,
                    language=language,
                    model=model,
                )
                logger.info(f"✅ STT initialized: {candidate}")
            
                if supervisor:
                    from core.providers.resilient_stt import ResilientSTTProxy
                    proxy = ResilientSTTProxy(
                        provider=instance,
                        supervisor=supervisor,
                        factory_fn=lambda c=candidate: cls._get_fresh_stt(c, language, model)
                    )
                    cls._cache[cache_key] = proxy
                    return proxy

                cls._cache[cache_key] = instance
                return instance
            except Exception as e:
                last_error = e
                if candidate == "azure" and "AZURE_SPEECH_KEY" in str(e):
                    logger.info("azure_stt_not_configured")
                logger.error(f"❌ Failed to initialize STT provider {candidate}: {e}")

        # Fallback to Groq STT if the whole chain fails.
        from livekit.plugins import groq
        logger.warning("⚠️ Falling back to Groq STT (whisper-large-v3-turbo, en)")
        if last_error:
            logger.debug("Last STT initialization error before Groq fallback: %s", last_error)
        return groq.STT(model="whisper-large-v3-turbo", language="en")

    @classmethod
    def get_tts(cls, provider_name: str, voice: str, model: str, supervisor: Optional[Any] = None, timeout: Optional[float] = None) -> Any:
        """Initialize TTS with fallback to OpenAI, optional resiliency, and connection timeout. Caches instances."""
        requested_provider = str(provider_name or "").strip().lower()
        cache_key = f"tts:{requested_provider}:{voice}:{model}:{id(supervisor) if supervisor else 'none'}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        timeout = timeout or cls.DEFAULT_TTS_TIMEOUT
        candidates = cls._resolve_tts_candidates(requested_provider)
        last_error: Optional[Exception] = None

        for candidate in candidates:
            if supervisor and supervisor.is_open(cls._provider_host(candidate)):
                logger.warning(
                    "circuit_breaker_open provider=%s falling_back",
                    cls._provider_host(candidate),
                )
                continue
            candidate_voice = voice if candidate == requested_provider else ""
            candidate_model = model if candidate == requested_provider else ""
            candidate_voice, candidate_model = cls._normalize_tts_params_for_provider(
                candidate,
                candidate_voice,
                candidate_model,
            )
            candidate_cache_key = (
                f"tts:{candidate}:{candidate_voice}:{candidate_model}:"
                f"{id(supervisor) if supervisor else 'none'}"
            )
            if candidate_cache_key in cls._cache:
                resolved = cls._cache[candidate_cache_key]
                cls._cache[cache_key] = resolved
                return resolved

            try:
                instance = get_tts_provider(
                    provider_name=candidate,
                    voice=candidate_voice,
                    model=candidate_model,
                )
                logger.info("✅ TTS initialized: %s", candidate)
                logger.info(
                    "🔊 tts_provider_active provider=%s model=%s voice=%s",
                    candidate,
                    candidate_model or "default",
                    candidate_voice or "default",
                )
                if candidate == cls._EDGE_TTS_PROVIDER and requested_provider != cls._EDGE_TTS_PROVIDER:
                    logger.warning(
                        "edge_tts_promoted_to_primary reason=all_primary_providers_failed requested_provider=%s",
                        requested_provider or "default",
                    )
                if candidate != requested_provider:
                    logger.warning(
                        "⚠️ TTS provider '%s' unavailable or deprioritized; using '%s'.",
                        requested_provider or "default",
                        candidate,
                    )

                if supervisor:
                    from core.providers.resilient_tts import ResilientTTSProxy

                    proxy = ResilientTTSProxy(
                        provider=instance,
                        supervisor=supervisor,
                        factory_fn=lambda c=candidate, v=candidate_voice, m=candidate_model: cls._get_fresh_tts(c, v, m),
                    )
                    cls._cache[candidate_cache_key] = proxy
                    cls._cache[cache_key] = proxy
                    return proxy

                cls._cache[candidate_cache_key] = instance
                cls._cache[cache_key] = instance
                return instance
            except Exception as e:
                last_error = e
                logger.error("❌ Failed to initialize TTS provider %s: %s", candidate, e)

        # Last-resort fallback to OpenAI when primary + Edge are unavailable.
        try:
            logger.error("❌ All configured TTS providers failed. Using OpenAI tts-1/alloy as last resort.")
            from livekit.plugins import openai

            return openai.TTS(model="tts-1", voice="alloy")
        except Exception as fe:
            if last_error:
                raise last_error
            raise fe

    @staticmethod
    def _get_fresh_stt(provider_name, language, model):
        return get_stt_provider(provider_name, language, model)
    
    @staticmethod
    def _get_fresh_tts(provider_name, voice, model):
        return get_tts_provider(provider_name, voice, model)
