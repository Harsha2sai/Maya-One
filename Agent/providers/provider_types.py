"""
Provider Type Enums
Defines all supported LLM, STT, and TTS providers for the LiveKit Agent
"""

from enum import Enum


class LLMProvider(str, Enum):
    """Supported LLM Providers"""
    OPENAI = "openai"
    GROQ = "groq"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"
    TOGETHER = "together"
    MISTRAL = "mistral"
    PERPLEXITY = "perplexity"
    OLLAMA = "ollama"
    VLLM = "vllm"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"


class STTProvider(str, Enum):
    """Supported Speech-to-Text Providers"""
    GROQ = "groq"
    OPENAI = "openai"
    DEEPGRAM = "deepgram"
    ASSEMBLYAI = "assemblyai"
    GOOGLE = "google"
    AZURE = "azure"
    AWS_TRANSCRIBE = "aws_transcribe"
    VOSK = "vosk"
    WHISPER_CPP = "whisper_cpp"


class TTSProvider(str, Enum):
    """Supported Text-to-Speech Providers"""
    GROQ = "groq"  # PlayAI
    ELEVENLABS = "elevenlabs"
    CARTESIA = "cartesia"
    DEEPGRAM = "deepgram"  # Aura
    OPENAI = "openai"
    AZURE = "azure"
    GOOGLE = "google"
    AWS_POLLY = "aws_polly"
    COQUI = "coqui"
    PIPER = "piper"
    EDGE_TTS = "edge_tts"  # Microsoft Edge TTS - FREE, no API key needed


# Default configurations for each provider type
LLM_DEFAULTS = {
    LLMProvider.OPENAI: {
        "model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
    },
    LLMProvider.GROQ: {
        "model": "llama-3.1-8b-instant",
        "env_key": "GROQ_API_KEY",
    },
    LLMProvider.GEMINI: {
        "model": "gemini-2.0-flash-exp",
        "env_key": "GEMINI_API_KEY",
    },
    LLMProvider.ANTHROPIC: {
        "model": "claude-3-5-sonnet-20241022",
        "env_key": "ANTHROPIC_API_KEY",
    },
    LLMProvider.AZURE_OPENAI: {
        "model": "gpt-4o",
        "env_key": "AZURE_OPENAI_API_KEY",
    },
    LLMProvider.AWS_BEDROCK: {
        "model": "anthropic.claude-3-sonnet-20240229-v1:0",
        "env_key": "AWS_ACCESS_KEY_ID",
    },
    LLMProvider.TOGETHER: {
        "model": "meta-llama/Llama-3-70b-chat-hf",
        "env_key": "TOGETHER_API_KEY",
    },
    LLMProvider.MISTRAL: {
        "model": "mistral-large-latest",
        "env_key": "MISTRAL_API_KEY",
    },
    LLMProvider.PERPLEXITY: {
        "model": "llama-3.1-sonar-large-128k-online",
        "env_key": "PERPLEXITY_API_KEY",
    },
    LLMProvider.OLLAMA: {
        "model": "llama3",
        "env_key": None,  # No API key needed for local
    },
    LLMProvider.VLLM: {
        "model": "meta-llama/Llama-3-8b-chat-hf",
        "env_key": None,  # No API key needed for local
    },
    LLMProvider.DEEPSEEK: {
        "model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
    },
    LLMProvider.QWEN: {
        "model": "qwen-turbo",
        "env_key": "QWEN_API_KEY",
    },
}

STT_DEFAULTS = {
    STTProvider.GROQ: {
        "model": "whisper-large-v3-turbo",
        "env_key": "GROQ_API_KEY",
    },
    STTProvider.OPENAI: {
        "model": "whisper-1",
        "env_key": "OPENAI_API_KEY",
    },
    STTProvider.DEEPGRAM: {
        "model": "nova-2",
        "env_key": "DEEPGRAM_API_KEY",
    },
    STTProvider.ASSEMBLYAI: {
        "model": "best",
        "env_key": "ASSEMBLYAI_API_KEY",
    },
    STTProvider.GOOGLE: {
        "model": "latest_long",
        "env_key": "GOOGLE_SPEECH_API_KEY",
    },
    STTProvider.AZURE: {
        "model": "en-US",
        "env_key": "AZURE_SPEECH_KEY",
    },
    STTProvider.AWS_TRANSCRIBE: {
        "model": "en-US",
        "env_key": "AWS_ACCESS_KEY_ID",
    },
    STTProvider.VOSK: {
        "model": "vosk-model-en-us-0.22",
        "env_key": None,  # Offline
    },
    STTProvider.WHISPER_CPP: {
        "model": "ggml-base.en.bin",
        "env_key": None,  # Offline
    },
}

TTS_DEFAULTS = {
    TTSProvider.GROQ: {
        "voice": "Arista-PlayAI",
        "env_key": "GROQ_API_KEY",
    },
    TTSProvider.ELEVENLABS: {
        "voice": "Rachel",
        "env_key": "ELEVENLABS_API_KEY",
    },
    TTSProvider.CARTESIA: {
        "voice": "79a125e8-cd45-4c13-8a67-188112f4dd22",
        "env_key": "CARTESIA_API_KEY",
    },
    TTSProvider.DEEPGRAM: {
        "voice": "aura-asteria-en",
        "env_key": "DEEPGRAM_API_KEY",
    },
    TTSProvider.OPENAI: {
        "voice": "alloy",
        "env_key": "OPENAI_API_KEY",
    },
    TTSProvider.AZURE: {
        "voice": "en-US-JennyNeural",
        "env_key": "AZURE_SPEECH_KEY",
    },
    TTSProvider.GOOGLE: {
        "voice": "en-US-Neural2-C",
        "env_key": "GOOGLE_TTS_API_KEY",
    },
    TTSProvider.AWS_POLLY: {
        "voice": "Joanna",
        "env_key": "AWS_ACCESS_KEY_ID",
    },
    TTSProvider.COQUI: {
        "voice": "tts_models/en/ljspeech/tacotron2-DDC",
        "env_key": None,  # Offline
    },
    TTSProvider.PIPER: {
        "voice": "en_US-lessac-medium",
        "env_key": None,  # Offline
    },
    TTSProvider.EDGE_TTS: {
        "voice": "en-US-JennyNeural",
        "env_key": None,  # FREE - No API key needed!
    },
}
