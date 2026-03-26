"""
STT (Speech-to-Text) Provider Factory Module
Supports multiple STT providers with dynamic selection at runtime.
All API keys are loaded from environment variables.

Supported Providers:
- Groq (Whisper Turbo)
- OpenAI Whisper
- Deepgram
- AssemblyAI
- Google Speech
- Azure Speech
- AWS Transcribe
- Vosk (offline)
- Whisper.cpp (offline)
"""

import inspect
import os
import logging
import re
import socket
from typing import Any, Optional, Dict

from .provider_types import STTProvider, STT_DEFAULTS

# Plugins are lazy-loaded in factory functions to prevent import deadlocks
# and ensure proper initialization context.

logger = logging.getLogger(__name__)


def is_valid_voice_transcript(text: str) -> bool:
    """Basic quality filter to drop obvious STT fragments/drift."""
    sample = (text or "").strip()
    if not sample:
        return False

    sample_lower = sample.lower()
    if re.search(r"\[(inaudible|noise|silence)\]", sample_lower):
        return False

    if re.search(r"([a-z])\1{5,}", sample_lower):
        return False

    filler_tokens = [w.strip(".,!?;:") for w in sample_lower.split()]
    if filler_tokens and all(token in {"um", "uh", "hmm", "erm"} for token in filler_tokens):
        return False

    words = sample.split()
    if len(words) == 1 and words[0].lower().strip(".,!?;:") in {"ai", "hey", "um", "uh"}:
        return False

    punct_count = sum(1 for ch in sample if ch in ".,?!;:")
    if words and (punct_count / max(1, len(words))) > 0.8:
        return False

    return True


def _resolve_deepgram_runtime_config(
    language: str,
    model: str,
    kwargs: Dict[str, Any],
    supported_params: Optional[set[str]] = None,
) -> tuple[str, str, Dict[str, Any]]:
    """Resolve Deepgram model/language and optional endpointing parameters from env."""
    default_language = language or STT_DEFAULTS[STTProvider.DEEPGRAM]["language"]
    resolved_language = os.getenv("DEEPGRAM_LANGUAGE", default_language)

    default_model = model or STT_DEFAULTS[STTProvider.DEEPGRAM]["model"]
    resolved_model = os.getenv("DEEPGRAM_MODEL", default_model)

    options: Dict[str, Any] = dict(kwargs)
    options.setdefault("interim_results", False)
    options.setdefault("smart_format", True)
    options.setdefault("no_delay", True)
    options.setdefault("punctuate", True)

    endpointing_ms = os.getenv("DEEPGRAM_ENDPOINTING_MS", "800").strip()
    endpoint_value = 800
    try:
        endpoint_value = int(endpointing_ms)
    except ValueError:
        logger.warning("⚠️ Invalid DEEPGRAM_ENDPOINTING_MS=%s; using 800", endpointing_ms)

    # Support both plugin variants: endpointing_ms (new) or endpointing (legacy).
    if "endpointing_ms" in supported_params:
        options.setdefault("endpointing_ms", endpoint_value)
    elif "endpointing" in supported_params:
        options.setdefault("endpointing", endpoint_value)

    return resolved_language, resolved_model, options


def probe_deepgram_connectivity(timeout_s: float = 2.0) -> tuple[bool, str]:
    """
    Lightweight runtime probe for Deepgram availability.
    Checks DNS resolution + TCP connect to api.deepgram.com:443.
    """
    host = "api.deepgram.com"
    try:
        socket.setdefaulttimeout(timeout_s)
        resolved = socket.getaddrinfo(host, 443)
        if not resolved:
            return False, "dns_resolve_empty"
        with socket.create_connection((host, 443), timeout=timeout_s):
            pass
        return True, "ok"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        try:
            socket.setdefaulttimeout(None)
        except Exception:
            pass


def build_stt_with_failover(
    *,
    provider_name: str,
    language: str,
    model: str,
    failover_enabled: bool = True,
    failover_target: str = "groq",
    probe_timeout_s: float = 2.0,
    **kwargs,
) -> tuple[Any, str, bool, Optional[str]]:
    """
    Build STT with startup failover support.
    Returns: (provider_instance, active_provider_name, degraded_mode, failover_reason)
    """
    requested = (provider_name or "").strip().lower()
    active_provider = requested
    degraded_mode = False
    failover_reason: Optional[str] = None
    secondary_fallback = str(os.getenv("STT_SECONDARY_FALLBACK", "azure")).strip().lower() or "azure"

    if failover_enabled and requested == "deepgram":
        ok, reason = probe_deepgram_connectivity(timeout_s=probe_timeout_s)
        if not ok:
            active_provider = (failover_target or "groq").strip().lower()
            degraded_mode = True
            failover_reason = f"deepgram_probe_failed:{reason}"
            logger.warning(
                "⚠️ STT failover: requested=%s active=%s reason=%s",
                requested,
                active_provider,
                failover_reason,
            )

    try:
        provider = get_stt_provider(
            provider_name=active_provider,
            language=language,
            model=model,
            **kwargs,
        )
        return provider, active_provider, degraded_mode, failover_reason
    except Exception as primary_err:
        if failover_enabled:
            fallback_chain: list[str] = []
            primary_target = (failover_target or "groq").strip().lower()
            for candidate in (primary_target, secondary_fallback):
                if candidate and candidate != active_provider and candidate not in fallback_chain:
                    fallback_chain.append(candidate)

            for fallback in fallback_chain:
                logger.warning(
                    "⚠️ STT failover fallback due to init failure: requested=%s active=%s error=%s",
                    requested,
                    fallback,
                    primary_err,
                )
                try:
                    provider = get_stt_provider(
                        provider_name=fallback,
                        language=language,
                        model=model,
                        **kwargs,
                    )
                    return (
                        provider,
                        fallback,
                        True,
                        failover_reason or f"stt_init_failed:{type(primary_err).__name__}",
                    )
                except Exception as fallback_err:
                    if fallback == "azure" and "AZURE_SPEECH_KEY" in str(fallback_err):
                        logger.info("azure_stt_not_configured")
                    primary_err = fallback_err
        raise


def is_deepgram_connection_error(err: Any) -> bool:
    """Heuristic matcher for Deepgram connectivity/runtime stream failures."""
    text = str(err or "").lower()
    markers = (
        "api.deepgram.com",
        "failed to connect to deepgram",
        "failed to recognize speech after",
        "clientconnectordnserror",
        "name or service not known",
        "temporary failure in name resolution",
        "net0001",
        "cannot write to closing transport",
        "connection closed unexpectedly",
    )
    return any(marker in text for marker in markers)


def get_stt_provider(
    provider_name: str,
    language: str = "en",
    model: str = "",
    **kwargs
) -> Any:
    """
    Factory function to get an STT provider instance.
    
    Args:
        provider_name: Name of the provider (e.g., "groq", "deepgram", "openai")
        language: Language code for transcription (default: "en")
        model: Model name to use (provider-specific, uses default if empty)
        **kwargs: Additional provider-specific arguments
    
    Returns:
        LiveKit-compatible STT instance
    
    Raises:
        ValueError: If provider is not supported or API key is missing
    
    Example:
        >>> stt = get_stt_provider("groq", language="en")
        >>> stt = get_stt_provider("deepgram", language="en", model="nova-2")
    """
    provider = provider_name.lower().strip()
    
    logger.info(f"🎙️ Initializing STT provider: {provider}")
    
    try:
        match provider:
            case "groq":
                return _get_groq_stt(language, model, **kwargs)
            case "openai" | "whisper":
                return _get_openai_stt(language, model, **kwargs)
            case "deepgram":
                return _get_deepgram_stt(language, model, **kwargs)
            case "assemblyai" | "assembly":
                return _get_assemblyai_stt(language, model, **kwargs)
            case "google" | "google_speech":
                return _get_google_stt(language, model, **kwargs)
            case "azure" | "azure_speech":
                return _get_azure_stt(language, model, **kwargs)
            case "aws_transcribe" | "aws" | "transcribe":
                return _get_aws_transcribe_stt(language, model, **kwargs)
            case "vosk":
                return _get_vosk_stt(language, model, **kwargs)
            case "whisper_cpp" | "whispercpp":
                return _get_whisper_cpp_stt(language, model, **kwargs)
            case _:
                raise ValueError(
                    f"❌ Unsupported STT provider: '{provider}'. "
                    f"Supported providers: {[p.value for p in STTProvider]}"
                )
    except ImportError as e:
        logger.error(f"❌ Missing plugin for {provider}: {e}")
        raise
    except ValueError as e:
        logger.error(f"❌ Configuration error for {provider}: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Failed to initialize {provider}: {e}")
        raise


def _validate_api_key(env_var: str, provider_name: str) -> str:
    """Validate that an API key exists in environment"""
    api_key = os.getenv(env_var)
    if not api_key:
        raise ValueError(
            f"❌ {env_var} not found in environment. "
            f"Please set {env_var} in your .env file."
        )
    return api_key


def _get_groq_stt(language: str, model: str, **kwargs) -> Any:
    """Initialize Groq STT (Whisper Turbo)"""
    try:
        from livekit.plugins import groq
    except ImportError:
        raise ImportError(
            "Groq plugin not installed. Install with: pip install livekit-plugins-groq"
        )
    
    _validate_api_key("GROQ_API_KEY", "Groq")
    model_name = model or STT_DEFAULTS[STTProvider.GROQ]["model"]
    
    logger.info(f"✅ Using Groq STT model: {model_name}, language: {language}")
    
    return groq.STT(
        model=model_name,
        language=language,
        **kwargs
    )


def _get_openai_stt(language: str, model: str, **kwargs) -> Any:
    """Initialize OpenAI Whisper STT"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    api_key = _validate_api_key("OPENAI_API_KEY", "OpenAI")
    model_name = model or STT_DEFAULTS[STTProvider.OPENAI]["model"]
    
    logger.info(f"✅ Using OpenAI Whisper model: {model_name}, language: {language}")
    
    return openai.STT(
        model=model_name,
        language=language,
        api_key=api_key,
        **kwargs
    )


def _get_deepgram_stt(language: str, model: str, **kwargs) -> Any:
    """Initialize Deepgram STT (streaming supported)"""
    try:
        from livekit.plugins import deepgram
    except ImportError:
        raise ImportError(
            "Deepgram plugin not installed. Install with: pip install livekit-plugins-deepgram"
        )
    
    api_key = _validate_api_key("DEEPGRAM_API_KEY", "Deepgram")
    supported_params = set(inspect.signature(deepgram.STT.__init__).parameters.keys())
    resolved_language, model_name, options = _resolve_deepgram_runtime_config(
        language,
        model,
        kwargs,
        supported_params=supported_params,
    )

    logger.info(
        "✅ Using Deepgram STT model: %s, language: %s, endpointing_ms=%s",
        model_name,
        resolved_language,
        options.get("endpointing_ms", options.get("endpointing")),
    )

    return deepgram.STT(
        model=model_name,
        language=resolved_language,
        api_key=api_key,
        **options,
    )


def _get_assemblyai_stt(language: str, model: str, **kwargs) -> Any:
    """Initialize AssemblyAI STT (streaming supported)"""
    try:
        from livekit.plugins import assemblyai
    except ImportError:
        raise ImportError(
            "AssemblyAI plugin not installed. Install with: pip install livekit-plugins-assemblyai"
        )
    
    api_key = _validate_api_key("ASSEMBLYAI_API_KEY", "AssemblyAI")
    
    logger.info(f"✅ Using AssemblyAI STT, language: {language}")
    
    return assemblyai.STT(
        api_key=api_key,
        **kwargs
    )


def _get_google_stt(language: str, model: str, **kwargs) -> Any:
    """Initialize Google Cloud Speech-to-Text"""
    try:
        from livekit.plugins import google
    except ImportError:
        raise ImportError(
            "Google plugin not installed. Install with: pip install livekit-plugins-google"
        )
    
    # Google uses service account credentials
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        logger.warning("⚠️ GOOGLE_APPLICATION_CREDENTIALS not set, using default credentials")
    
    logger.info(f"✅ Using Google Speech-to-Text, language: {language}")
    
    return google.STT(
        language=language,
        **kwargs
    )


def _get_azure_stt(language: str, model: str, **kwargs) -> Any:
    """Initialize Azure Speech-to-Text"""
    try:
        from livekit.plugins import azure
    except ImportError:
        raise ImportError(
            "Azure plugin not installed. Install with: pip install livekit-plugins-azure"
        )
    
    api_key = _validate_api_key("AZURE_SPEECH_KEY", "Azure Speech")
    region = os.getenv("AZURE_SPEECH_REGION", "eastus")
    
    logger.info(f"✅ Using Azure Speech-to-Text, region: {region}, language: {language}")
    
    return azure.STT(
        speech_key=api_key,
        speech_region=region,
        language=language,
        **kwargs
    )


def _get_aws_transcribe_stt(language: str, model: str, **kwargs) -> Any:
    """Initialize AWS Transcribe"""
    try:
        from livekit.plugins import aws
    except ImportError:
        raise ImportError(
            "AWS plugin not installed. Install with: pip install livekit-plugins-aws"
        )
    
    _validate_api_key("AWS_ACCESS_KEY_ID", "AWS")
    _validate_api_key("AWS_SECRET_ACCESS_KEY", "AWS")
    region = os.getenv("AWS_REGION", "us-east-1")
    
    # AWS Transcribe requires full language codes in BCP-47 format
    # Map common 2-letter codes to their appropriate regional variants
    AWS_LANGUAGE_MAPPINGS = {
        "en": "en-US",
        "es": "es-US",
        "fr": "fr-FR",
        "de": "de-DE",
        "it": "it-IT",
        "pt": "pt-BR",  # Brazilian Portuguese is more common
        "zh": "zh-CN",  # Simplified Chinese (Mandarin)
        "ja": "ja-JP",
        "ko": "ko-KR",
        "ar": "ar-SA",  # Modern Standard Arabic
        "hi": "hi-IN",
        "ru": "ru-RU",
        "nl": "nl-NL",
        "sv": "sv-SE",
        "no": "no-NO",
        "da": "da-DK",
        "fi": "fi-FI",
        "pl": "pl-PL",
        "tr": "tr-TR",
        "th": "th-TH",
        "vi": "vi-VN",
    }
    
    # Validate and convert language code
    if "-" in language:
        # Already has region, validate format
        if not re.match(r'^[a-z]{2}-[A-Z]{2}$', language):
            logger.warning(
                f"⚠️ Language code '{language}' may not be properly formatted. "
                f"Expected format: 'xx-YY' (e.g., 'en-US'). "
                f"See: https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html"
            )
        aws_language = language
    else:
        # Map 2-letter code to regional variant
        if language.lower() in AWS_LANGUAGE_MAPPINGS:
            aws_language = AWS_LANGUAGE_MAPPINGS[language.lower()]
            logger.info(f"📝 Mapped '{language}' to AWS language code: {aws_language}")
        else:
            raise ValueError(
                f"❌ Unsupported language code: '{language}'. "
                f"Please provide full BCP-47 format (e.g., 'en-US', '{language}-XX') or use a supported code. "
                f"Supported 2-letter codes: {', '.join(sorted(AWS_LANGUAGE_MAPPINGS.keys()))}. "
                f"Full list: https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html"
            )
    
    logger.info(f"✅ Using AWS Transcribe, region: {region}, language: {aws_language}")
    
    return aws.STT(
        region=region,
        language_code=aws_language,
        **kwargs
    )


def _get_vosk_stt(language: str, model: str, **kwargs) -> Any:
    """Initialize Vosk STT (offline, local)"""
    logger.warning("⚠️ Vosk STT requires local model installation")
    
    # Vosk is not a standard LiveKit plugin, this is a placeholder
    # for custom implementation
    model_path = model or os.getenv("VOSK_MODEL_PATH", "")
    
    if not model_path:
        raise ValueError(
            "❌ VOSK_MODEL_PATH not set. Download a model from "
            "https://alphacephei.com/vosk/models and set the path."
        )
    
    logger.info(f"✅ Using Vosk STT (offline), model: {model_path}")
    
    # Return a placeholder - implement custom Vosk wrapper if needed
    raise NotImplementedError(
        "Vosk STT integration requires custom implementation. "
        "Use a different provider or implement VoskSTT wrapper."
    )


def _get_whisper_cpp_stt(language: str, model: str, **kwargs) -> Any:
    """Initialize Whisper.cpp STT (offline, local)"""
    logger.warning("⚠️ Whisper.cpp STT requires local model installation")
    
    model_path = model or os.getenv("WHISPER_CPP_MODEL_PATH", "")
    
    if not model_path:
        raise ValueError(
            "❌ WHISPER_CPP_MODEL_PATH not set. Download a model from "
            "https://huggingface.co/ggerganov/whisper.cpp and set the path."
        )
    
    logger.info(f"✅ Using Whisper.cpp STT (offline), model: {model_path}")
    
    # Return a placeholder - implement custom Whisper.cpp wrapper if needed
    raise NotImplementedError(
        "Whisper.cpp STT integration requires custom implementation. "
        "Use a different provider or implement WhisperCppSTT wrapper."
    )


# Provider information for documentation
STT_PROVIDER_INFO: Dict[str, Dict] = {
    "groq": {
        "name": "Groq (Whisper Turbo)",
        "default_model": STT_DEFAULTS[STTProvider.GROQ]["model"],
        "env_vars": ["GROQ_API_KEY"],
        "models": ["whisper-large-v3-turbo", "whisper-large-v3"],
        "streaming": True,
        "plugin": "livekit-plugins-groq",
    },
    "openai": {
        "name": "OpenAI Whisper",
        "default_model": STT_DEFAULTS[STTProvider.OPENAI]["model"],
        "env_vars": ["OPENAI_API_KEY"],
        "models": ["whisper-1"],
        "streaming": False,
        "plugin": "livekit-plugins-openai",
    },
    "deepgram": {
        "name": "Deepgram",
        "default_model": STT_DEFAULTS[STTProvider.DEEPGRAM]["model"],
        "env_vars": ["DEEPGRAM_API_KEY"],
        "models": ["nova-2", "nova", "enhanced", "base"],
        "streaming": True,
        "plugin": "livekit-plugins-deepgram",
    },
    "assemblyai": {
        "name": "AssemblyAI",
        "default_model": STT_DEFAULTS[STTProvider.ASSEMBLYAI]["model"],
        "env_vars": ["ASSEMBLYAI_API_KEY"],
        "models": ["best", "nano"],
        "streaming": True,
        "plugin": "livekit-plugins-assemblyai",
    },
    "google": {
        "name": "Google Cloud Speech",
        "default_model": STT_DEFAULTS[STTProvider.GOOGLE]["model"],
        "env_vars": ["GOOGLE_APPLICATION_CREDENTIALS"],
        "models": ["latest_long", "latest_short", "command_and_search"],
        "streaming": True,
        "plugin": "livekit-plugins-google",
    },
    "azure": {
        "name": "Azure Speech",
        "default_model": STT_DEFAULTS[STTProvider.AZURE]["model"],
        "env_vars": ["AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"],
        "models": ["en-US", "en-GB", "de-DE", "fr-FR"],
        "streaming": True,
        "plugin": "livekit-plugins-azure",
    },
    "aws_transcribe": {
        "name": "AWS Transcribe",
        "default_model": STT_DEFAULTS[STTProvider.AWS_TRANSCRIBE]["model"],
        "env_vars": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"],
        "models": ["en-US", "en-GB", "es-US"],
        "streaming": True,
        "plugin": "livekit-plugins-aws",
    },
    "vosk": {
        "name": "Vosk (Offline)",
        "default_model": STT_DEFAULTS[STTProvider.VOSK]["model"],
        "env_vars": ["VOSK_MODEL_PATH"],
        "models": ["vosk-model-en-us-0.22", "vosk-model-small-en-us-0.15"],
        "streaming": True,
        "plugin": "custom",
        "offline": True,
    },
    "whisper_cpp": {
        "name": "Whisper.cpp (Offline)",
        "default_model": STT_DEFAULTS[STTProvider.WHISPER_CPP]["model"],
        "env_vars": ["WHISPER_CPP_MODEL_PATH"],
        "models": ["ggml-base.en.bin", "ggml-small.en.bin", "ggml-medium.en.bin"],
        "streaming": False,
        "plugin": "custom",
        "offline": True,
    },
}


def list_stt_providers() -> None:
    """Print information about all available STT providers"""
    print("\n🎙️ Available STT Providers:\n")
    for provider_id, info in STT_PROVIDER_INFO.items():
        print(f"  {provider_id.upper()}")
        print(f"    Name: {info['name']}")
        print(f"    Default Model: {info['default_model']}")
        print(f"    Available Models: {', '.join(info['models'])}")
        print(f"    Streaming: {'✅' if info['streaming'] else '❌'}")
        print(f"    Offline: {'✅' if info.get('offline') else '❌'}")
        print(f"    Required Env Vars: {', '.join(info['env_vars'])}")
        print(f"    Plugin: {info['plugin']}")
        print()


if __name__ == "__main__":
    list_stt_providers()
