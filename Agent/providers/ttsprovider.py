"""
TTS (Text-to-Speech) Provider Factory Module
Supports multiple TTS providers with dynamic selection at runtime.
All API keys are loaded from environment variables.

Supported Providers:
- Groq (PlayAI)
- ElevenLabs
- Cartesia
- Deepgram Aura
- OpenAI TTS
- Azure Neural TTS
- Google TTS
- Amazon Polly
- Coqui TTS (offline)
- Piper TTS (offline)
"""

import os
import logging
from typing import Any, Optional, Dict

from .provider_types import TTSProvider, TTS_DEFAULTS

logger = logging.getLogger(__name__)


def get_tts_provider(
    provider_name: str,
    voice: str = "",
    model: str = "",
    **kwargs
) -> Any:
    """
    Factory function to get a TTS provider instance.
    
    Args:
        provider_name: Name of the provider (e.g., "elevenlabs", "cartesia", "openai")
        voice: Voice ID or name to use (provider-specific, uses default if empty)
        model: Model name to use (provider-specific, uses default if empty)
        **kwargs: Additional provider-specific arguments
    
    Returns:
        LiveKit-compatible TTS instance
    
    Raises:
        ValueError: If provider is not supported or API key is missing
    
    Example:
        >>> tts = get_tts_provider("elevenlabs", voice="Rachel")
        >>> tts = get_tts_provider("cartesia", voice="79a125e8-cd45-4c13-8a67-188112f4dd22")
    """
    provider = provider_name.lower().strip()
    
    logger.info(f"🔊 Initializing TTS provider: {provider}")
    
    try:
        match provider:
            case "groq" | "playai":
                return _get_groq_tts(voice, model, **kwargs)
            case "noop" | "none" | "text_only":
                logger.info("✅ Using No-Op TTS (Text Only Mode)")
                return None
            case "elevenlabs" | "eleven":
                return _get_elevenlabs_tts(voice, model, **kwargs)
            case "cartesia":
                return _get_cartesia_tts(voice, model, **kwargs)
            case "deepgram" | "aura":
                return _get_deepgram_tts(voice, model, **kwargs)
            case "openai":
                return _get_openai_tts(voice, model, **kwargs)
            case "azure" | "azure_tts":
                return _get_azure_tts(voice, model, **kwargs)
            case "google" | "google_tts":
                return _get_google_tts(voice, model, **kwargs)
            case "aws_polly" | "polly" | "aws":
                return _get_polly_tts(voice, model, **kwargs)
            case "coqui":
                return _get_coqui_tts(voice, model, **kwargs)
            case "piper":
                return _get_piper_tts(voice, model, **kwargs)
            case "edge" | "edge_tts" | "edgetts" | "microsoft":
                return _get_edge_tts(voice, model, **kwargs)
            case _:
                raise ValueError(
                    f"❌ Unsupported TTS provider: '{provider}'. "
                    f"Supported providers: {[p.value for p in TTSProvider]}"
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


def _get_groq_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize Groq TTS (PlayAI)"""
    try:
        from livekit.plugins import groq
    except ImportError:
        raise ImportError(
            "Groq plugin not installed. Install with: pip install livekit-plugins-groq"
        )
    
    _validate_api_key("GROQ_API_KEY", "Groq")
    voice_name = voice or TTS_DEFAULTS[TTSProvider.GROQ]["voice"]
    
    logger.info(f"✅ Using Groq TTS (PlayAI), voice: {voice_name}")
    
    return groq.TTS(
        voice=voice_name,
        **kwargs
    )


def _get_elevenlabs_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize ElevenLabs TTS"""
    try:
        from livekit.plugins import elevenlabs
    except ImportError:
        raise ImportError(
            "ElevenLabs plugin not installed. Install with: pip install livekit-plugins-elevenlabs"
        )
    
    api_key = _validate_api_key("ELEVENLABS_API_KEY", "ElevenLabs")
    voice_name = voice or TTS_DEFAULTS[TTSProvider.ELEVENLABS]["voice"]
    model_name = model or "eleven_multilingual_v2"
    
    logger.info(f"✅ Using ElevenLabs TTS, voice: {voice_name}, model: {model_name}")
    
    return elevenlabs.TTS(
        voice=voice_name,
        model=model_name,
        api_key=api_key,
        **kwargs
    )


def _get_cartesia_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize Cartesia TTS"""
    try:
        from livekit.plugins import cartesia
    except ImportError:
        raise ImportError(
            "Cartesia plugin not installed. Install with: pip install livekit-plugins-cartesia"
        )
    
    api_key = _validate_api_key("CARTESIA_API_KEY", "Cartesia")
    voice_id = voice or TTS_DEFAULTS[TTSProvider.CARTESIA]["voice"]
    
    logger.info(f"✅ Using Cartesia TTS, voice: {voice_id}")
    
    return cartesia.TTS(
        voice=voice_id,
        api_key=api_key,
        **kwargs
    )


def _get_deepgram_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize Deepgram Aura TTS"""
    try:
        from livekit.plugins import deepgram
    except ImportError:
        raise ImportError(
            "Deepgram plugin not installed. Install with: pip install livekit-plugins-deepgram"
        )
    
    api_key = _validate_api_key("DEEPGRAM_API_KEY", "Deepgram")
    voice_name = voice or TTS_DEFAULTS[TTSProvider.DEEPGRAM]["voice"]
    
    logger.info(f"✅ Using Deepgram Aura TTS, voice: {voice_name}")
    
    return deepgram.TTS(
        voice=voice_name,
        api_key=api_key,
        **kwargs
    )


def _get_openai_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize OpenAI TTS"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    api_key = _validate_api_key("OPENAI_API_KEY", "OpenAI")
    voice_name = voice or TTS_DEFAULTS[TTSProvider.OPENAI]["voice"]
    model_name = model or "tts-1"
    
    logger.info(f"✅ Using OpenAI TTS, voice: {voice_name}, model: {model_name}")
    
    return openai.TTS(
        voice=voice_name,
        model=model_name,
        api_key=api_key,
        **kwargs
    )


def _get_azure_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize Azure Neural TTS"""
    try:
        from livekit.plugins import azure
    except ImportError:
        raise ImportError(
            "Azure plugin not installed. Install with: pip install livekit-plugins-azure"
        )
    
    api_key = _validate_api_key("AZURE_SPEECH_KEY", "Azure Speech")
    region = os.getenv("AZURE_SPEECH_REGION", "eastus")
    voice_name = voice or TTS_DEFAULTS[TTSProvider.AZURE]["voice"]
    
    logger.info(f"✅ Using Azure Neural TTS, voice: {voice_name}, region: {region}")
    
    return azure.TTS(
        speech_key=api_key,
        speech_region=region,
        voice=voice_name,
        **kwargs
    )


def _get_google_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize Google Cloud TTS"""
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
    
    voice_name = voice or TTS_DEFAULTS[TTSProvider.GOOGLE]["voice"]
    
    logger.info(f"✅ Using Google Cloud TTS, voice: {voice_name}")
    
    return google.TTS(
        voice=voice_name,
        **kwargs
    )


def _get_polly_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize Amazon Polly TTS"""
    try:
        from livekit.plugins import aws
    except ImportError:
        raise ImportError(
            "AWS plugin not installed. Install with: pip install livekit-plugins-aws"
        )
    
    _validate_api_key("AWS_ACCESS_KEY_ID", "AWS")
    _validate_api_key("AWS_SECRET_ACCESS_KEY", "AWS")
    region = os.getenv("AWS_REGION", os.getenv("POLLY_REGION", "us-east-1"))
    voice_name = voice or TTS_DEFAULTS[TTSProvider.AWS_POLLY]["voice"]
    engine = kwargs.pop("engine", "neural")  # neural or standard
    
    logger.info(f"✅ Using Amazon Polly TTS, voice: {voice_name}, region: {region}, engine: {engine}")
    
    return aws.TTS(
        voice=voice_name,
        region=region,
        engine=engine,
        **kwargs
    )


def _get_coqui_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize Coqui TTS (offline, local)"""
    logger.warning("⚠️ Coqui TTS requires local model installation")
    
    model_name = voice or model or os.getenv("COQUI_MODEL", "")
    
    if not model_name:
        model_name = TTS_DEFAULTS[TTSProvider.COQUI]["voice"]
    
    logger.info(f"✅ Using Coqui TTS (offline), model: {model_name}")
    
    # Coqui is not a standard LiveKit plugin
    raise NotImplementedError(
        "Coqui TTS integration requires custom implementation. "
        "Use a different provider or implement CoquiTTS wrapper."
    )


def _get_piper_tts(voice: str, model: str, **kwargs) -> Any:
    """Initialize Piper TTS (offline, local)"""
    logger.warning("⚠️ Piper TTS requires local model installation")
    
    model_path = model or os.getenv("PIPER_MODEL_PATH", "")
    voice_name = voice or TTS_DEFAULTS[TTSProvider.PIPER]["voice"]
    
    if not model_path:
        raise ValueError(
            "❌ PIPER_MODEL_PATH not set. Download a model from "
            "https://github.com/rhasspy/piper/releases and set the path."
        )
    
    logger.info(f"✅ Using Piper TTS (offline), voice: {voice_name}, model: {model_path}")
    
    # Piper is not a standard LiveKit plugin
    raise NotImplementedError(
        "Piper TTS integration requires custom implementation. "
        "Use a different provider or implement PiperTTS wrapper."
    )


def _get_edge_tts(voice: str, model: str, **kwargs) -> Any:
    """
    Initialize Edge-TTS (Microsoft Edge's free TTS API).
    
    Features:
    - FREE - No API key required!
    - High-quality neural voices (same as Azure Cognitive Services)
    - Multiple voices and languages supported
    
    Args:
        voice: Voice ID (e.g., "en-US-JennyNeural", "en-US-GuyNeural")
        model: Not used for Edge-TTS
        **kwargs: Additional arguments passed to EdgeTTS
            - rate: Speech rate (e.g., "+10%", "-20%")
            - volume: Volume adjustment (e.g., "+10%")
            - pitch: Pitch adjustment (e.g., "+5Hz")
    
    Returns:
        EdgeTTS instance
    """
    try:
        from .edge_tts_provider import EdgeTTS, EDGE_TTS_VOICES, DEFAULT_VOICE
    except ImportError:
        raise ImportError(
            "edge-tts library not installed. Install with: pip install edge-tts"
        )
    
    # Use provided voice or default
    voice_name = voice or TTS_DEFAULTS[TTSProvider.EDGE_TTS]["voice"]
    
    # Extract Edge-TTS specific kwargs
    rate = kwargs.pop("rate", "+0%")
    volume = kwargs.pop("volume", "+0%")
    pitch = kwargs.pop("pitch", "+0Hz")
    
    logger.info(f"✅ Using Edge-TTS (FREE), voice: {voice_name}")
    
    return EdgeTTS(
        voice=voice_name,
        rate=rate,
        volume=volume,
        pitch=pitch,
    )


# Provider information for documentation
TTS_PROVIDER_INFO: Dict[str, Dict] = {
    "groq": {
        "name": "Groq (PlayAI)",
        "default_voice": TTS_DEFAULTS[TTSProvider.GROQ]["voice"],
        "env_vars": ["GROQ_API_KEY"],
        "voices": ["Arista-PlayAI", "Angelo-PlayAI", "Arsenio-PlayAI"],
        "streaming": True,
        "plugin": "livekit-plugins-groq",
    },
    "elevenlabs": {
        "name": "ElevenLabs",
        "default_voice": TTS_DEFAULTS[TTSProvider.ELEVENLABS]["voice"],
        "env_vars": ["ELEVENLABS_API_KEY"],
        "voices": ["Rachel", "Drew", "Clyde", "Paul", "Domi", "Dave", "Bella"],
        "streaming": True,
        "plugin": "livekit-plugins-elevenlabs",
    },
    "cartesia": {
        "name": "Cartesia",
        "default_voice": TTS_DEFAULTS[TTSProvider.CARTESIA]["voice"],
        "env_vars": ["CARTESIA_API_KEY"],
        "voices": ["79a125e8-cd45-4c13-8a67-188112f4dd22"],
        "streaming": True,
        "plugin": "livekit-plugins-cartesia",
    },
    "deepgram": {
        "name": "Deepgram Aura",
        "default_voice": TTS_DEFAULTS[TTSProvider.DEEPGRAM]["voice"],
        "env_vars": ["DEEPGRAM_API_KEY"],
        "voices": ["aura-asteria-en", "aura-luna-en", "aura-stella-en", "aura-athena-en"],
        "streaming": True,
        "plugin": "livekit-plugins-deepgram",
    },
    "openai": {
        "name": "OpenAI TTS",
        "default_voice": TTS_DEFAULTS[TTSProvider.OPENAI]["voice"],
        "env_vars": ["OPENAI_API_KEY"],
        "voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        "streaming": True,
        "plugin": "livekit-plugins-openai",
    },
    "azure": {
        "name": "Azure Neural TTS",
        "default_voice": TTS_DEFAULTS[TTSProvider.AZURE]["voice"],
        "env_vars": ["AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"],
        "voices": ["en-US-JennyNeural", "en-US-GuyNeural", "en-GB-SoniaNeural"],
        "streaming": True,
        "plugin": "livekit-plugins-azure",
    },
    "google": {
        "name": "Google Cloud TTS",
        "default_voice": TTS_DEFAULTS[TTSProvider.GOOGLE]["voice"],
        "env_vars": ["GOOGLE_APPLICATION_CREDENTIALS"],
        "voices": ["en-US-Neural2-C", "en-US-Neural2-F", "en-GB-Neural2-A"],
        "streaming": True,
        "plugin": "livekit-plugins-google",
    },
    "aws_polly": {
        "name": "Amazon Polly",
        "default_voice": TTS_DEFAULTS[TTSProvider.AWS_POLLY]["voice"],
        "env_vars": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "POLLY_REGION"],
        "voices": ["Joanna", "Matthew", "Ivy", "Kendra", "Salli"],
        "streaming": True,
        "plugin": "livekit-plugins-aws",
    },
    "coqui": {
        "name": "Coqui TTS (Offline)",
        "default_voice": TTS_DEFAULTS[TTSProvider.COQUI]["voice"],
        "env_vars": ["COQUI_MODEL"],
        "voices": ["tts_models/en/ljspeech/tacotron2-DDC"],
        "streaming": False,
        "plugin": "custom",
        "offline": True,
    },
    "piper": {
        "name": "Piper TTS (Offline)",
        "default_voice": TTS_DEFAULTS[TTSProvider.PIPER]["voice"],
        "env_vars": ["PIPER_MODEL_PATH"],
        "voices": ["en_US-lessac-medium", "en_US-amy-medium"],
        "streaming": True,
        "plugin": "custom",
        "offline": True,
    },
    "edge_tts": {
        "name": "Microsoft Edge TTS (FREE)",
        "default_voice": TTS_DEFAULTS[TTSProvider.EDGE_TTS]["voice"],
        "env_vars": [],  # No API key required!
        "voices": [
            "en-US-JennyNeural",
            "en-US-GuyNeural",
            "en-US-AriaNeural",
            "en-US-DavisNeural",
            "en-GB-SoniaNeural",
            "en-GB-RyanNeural",
            "en-IN-NeerjaNeural",
            "en-IN-PrabhatNeural",
        ],
        "streaming": False,
        "plugin": "edge-tts",
        "offline": False,
        "free": True,  # Highlight that it's FREE!
    },
}


def list_tts_providers() -> None:
    """Print information about all available TTS providers"""
    print("\n🔊 Available TTS Providers:\n")
    for provider_id, info in TTS_PROVIDER_INFO.items():
        print(f"  {provider_id.upper()}")
        print(f"    Name: {info['name']}")
        print(f"    Default Voice: {info['default_voice']}")
        print(f"    Available Voices: {', '.join(info['voices'][:5])}")
        print(f"    Streaming: {'✅' if info['streaming'] else '❌'}")
        print(f"    Offline: {'✅' if info.get('offline') else '❌'}")
        print(f"    Required Env Vars: {', '.join(info['env_vars'])}")
        print(f"    Plugin: {info['plugin']}")
        print()


if __name__ == "__main__":
    list_tts_providers()
