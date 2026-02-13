"""
Example Usage of Pluggable Providers
Demonstrates how to dynamically switch between LLM, STT, and TTS providers.

Run this file to see available providers and test the configuration:
    python providers/example_usage.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers import (
    get_llm_provider,
    get_stt_provider,
    get_tts_provider,
    LLMProvider,
    STTProvider,
    TTSProvider,
    list_llm_providers,
    list_stt_providers,
    list_tts_providers,
)
from config.settings import settings


def example_basic_usage():
    """
    Basic usage example: Get providers using default settings from .env
    """
    print("\n" + "=" * 60)
    print("📚 EXAMPLE 1: Basic Usage (from .env settings)")
    print("=" * 60)
    
    # These read from environment variables
    print(f"\nCurrent settings:")
    print(f"  LLM Provider: {settings.llm_provider}")
    print(f"  STT Provider: {settings.stt_provider}")
    print(f"  TTS Provider: {settings.tts_provider}")
    

def example_explicit_providers():
    """
    Explicit usage example: Specify providers directly in code
    """
    print("\n" + "=" * 60)
    print("📚 EXAMPLE 2: Explicit Provider Selection")
    print("=" * 60)
    
    print("""
# LLM Provider Examples
llm = get_llm_provider("groq", model="llama-3.3-70b-versatile")
llm = get_llm_provider("openai", model="gpt-4o", temperature=0.5)
llm = get_llm_provider("gemini", model="gemini-2.0-flash-exp")
llm = get_llm_provider("anthropic", model="claude-3-5-sonnet-20241022")
llm = get_llm_provider("ollama", model="llama3")  # Local

# STT Provider Examples
stt = get_stt_provider("groq", language="en")
stt = get_stt_provider("deepgram", language="en", model="nova-2")
stt = get_stt_provider("openai", language="en")  # Whisper
stt = get_stt_provider("assemblyai", language="en")

# TTS Provider Examples
tts = get_tts_provider("elevenlabs", voice="Rachel")
tts = get_tts_provider("cartesia", voice="79a125e8-cd45-4c13-8a67-188112f4dd22")
tts = get_tts_provider("openai", voice="alloy")
tts = get_tts_provider("deepgram", voice="aura-asteria-en")
""")


def example_agent_session():
    """
    Agent Session example: Complete session with all providers
    """
    print("\n" + "=" * 60)
    print("📚 EXAMPLE 3: Complete Agent Session")
    print("=" * 60)
    
    print("""
from providers import get_llm_provider, get_stt_provider, get_tts_provider
from config.settings import settings
from livekit.agents import AgentSession
from livekit.plugins import silero

# Method 1: Using settings from .env
session = AgentSession(
    stt=get_stt_provider(
        provider_name=settings.stt_provider,
        language=settings.stt_language,
        model=settings.stt_model,
    ),
    llm=get_llm_provider(
        provider_name=settings.llm_provider,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
    ),
    tts=get_tts_provider(
        provider_name=settings.tts_provider,
        voice=settings.tts_voice,
        model=settings.tts_model,
    ),
    vad=silero.VAD.load(),
)

# Method 2: Explicit configuration (for testing different setups)
session = AgentSession(
    stt=get_stt_provider("deepgram", language="en", model="nova-2"),
    llm=get_llm_provider("openai", model="gpt-4o", temperature=0.7),
    tts=get_tts_provider("elevenlabs", voice="Rachel"),
    vad=silero.VAD.load(),
)
""")


def example_env_configuration():
    """
    Environment configuration example
    """
    print("\n" + "=" * 60)
    print("📚 EXAMPLE 4: .env Configuration")
    print("=" * 60)
    
    print("""
# To switch providers, simply update your .env file:

# Use Groq for everything (fast, cheap)
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
STT_PROVIDER=groq
STT_MODEL=whisper-large-v3-turbo
TTS_PROVIDER=groq
TTS_VOICE=Arista-PlayAI

# Use OpenAI for everything (premium quality)
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
STT_PROVIDER=openai
STT_MODEL=whisper-1
TTS_PROVIDER=openai
TTS_VOICE=nova

# Mixed: Best of each
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-5-sonnet-20241022
STT_PROVIDER=deepgram
STT_MODEL=nova-2
TTS_PROVIDER=elevenlabs
TTS_VOICE=Rachel

# Local/Offline setup
LLM_PROVIDER=ollama
LLM_MODEL=llama3
STT_PROVIDER=groq  # Or vosk for fully offline
TTS_PROVIDER=openai  # Or piper for fully offline
""")


def example_provider_enums():
    """
    Provider enum usage example
    """
    print("\n" + "=" * 60)
    print("📚 EXAMPLE 5: Using Provider Enums (Type Safety)")
    print("=" * 60)
    
    print("""
from providers import LLMProvider, STTProvider, TTSProvider

# Use enums for type safety
llm = get_llm_provider(LLMProvider.GROQ.value, model="llama3-70b-8192")
stt = get_stt_provider(STTProvider.DEEPGRAM.value, language="en")
tts = get_tts_provider(TTSProvider.ELEVENLABS.value, voice="Rachel")

# Check available options
for provider in LLMProvider:
    print(f"LLM: {provider.value}")

for provider in STTProvider:
    print(f"STT: {provider.value}")

for provider in TTSProvider:
    print(f"TTS: {provider.value}")
""")


def main():
    """Run all examples"""
    print("\n" + "🎯" * 30)
    print("  LIVEKIT PLUGGABLE PROVIDERS - USAGE EXAMPLES")
    print("🎯" * 30)
    
    example_basic_usage()
    example_explicit_providers()
    example_agent_session()
    example_env_configuration()
    example_provider_enums()
    
    print("\n" + "=" * 60)
    print("📋 AVAILABLE PROVIDERS")
    print("=" * 60)
    
    list_llm_providers()
    list_stt_providers()
    list_tts_providers()


if __name__ == "__main__":
    main()
