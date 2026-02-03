"""
Centralized Settings Module
Loads all configuration from environment variables and provides
a unified configuration interface for the LiveKit Agent.

Usage:
    from config.settings import settings
    
    llm = get_llm_provider(settings.llm_provider, settings.llm_model)
    stt = get_stt_provider(settings.stt_provider, settings.stt_language)
    tts = get_tts_provider(settings.tts_provider, settings.tts_voice)
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class ProviderSettings:
    """Settings for a specific provider type (LLM, STT, or TTS)"""
    provider: str
    model: str = ""
    voice: str = ""
    language: str = "en"
    temperature: float = 0.7
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Settings:
    """
    Centralized configuration for the LiveKit Agent.
    All settings are loaded from environment variables.
    """
    
    # ==================== USER SETTINGS ====================
    user_name: str = field(default_factory=lambda: os.getenv("USER_NAME", "User"))
    
    # ==================== LLM SETTINGS ====================
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "groq"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "llama-3.1-8b-instant"))
    llm_temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.7")))
    
    # ==================== STT SETTINGS ====================
    stt_provider: str = field(default_factory=lambda: os.getenv("STT_PROVIDER", "deepgram"))
    stt_model: str = field(default_factory=lambda: os.getenv("STT_MODEL", "nova-2"))
    stt_language: str = field(default_factory=lambda: os.getenv("STT_LANGUAGE", "en"))
    
    # ==================== TTS SETTINGS ====================
    tts_provider: str = field(default_factory=lambda: os.getenv("TTS_PROVIDER", "edge_tts"))
    tts_model: str = field(default_factory=lambda: os.getenv("TTS_MODEL", "tts-1"))
    tts_voice: str = field(default_factory=lambda: os.getenv("TTS_VOICE", "en-US-JennyNeural"))
    
    # ==================== MEMORY SETTINGS ====================
    mem0_enabled: bool = field(default_factory=lambda: bool(os.getenv("MEM0_API_KEY")))
    mem0_api_key: Optional[str] = field(default_factory=lambda: os.getenv("MEM0_API_KEY"))
    
    # ==================== MCP SETTINGS ====================
    n8n_mcp_server_url: Optional[str] = field(default_factory=lambda: os.getenv("N8N_MCP_SERVER_URL"))
    
    # ==================== LIVEKIT SETTINGS ====================
    livekit_url: Optional[str] = field(default_factory=lambda: os.getenv("LIVEKIT_URL"))
    livekit_api_key: Optional[str] = field(default_factory=lambda: os.getenv("LIVEKIT_API_KEY"))
    livekit_api_secret: Optional[str] = field(default_factory=lambda: os.getenv("LIVEKIT_API_SECRET"))
    
    # ==================== TOOL SETTINGS ====================
    weather_timeout: int = field(default_factory=lambda: int(os.getenv("WEATHER_TIMEOUT", "5")))
    email_timeout: int = field(default_factory=lambda: int(os.getenv("EMAIL_TIMEOUT", "10")))
    
    @property
    def llm_settings(self) -> ProviderSettings:
        """Get LLM provider settings as a structured object"""
        return ProviderSettings(
            provider=self.llm_provider,
            model=self.llm_model,
            temperature=self.llm_temperature,
        )
    
    @property
    def stt_settings(self) -> ProviderSettings:
        """Get STT provider settings as a structured object"""
        return ProviderSettings(
            provider=self.stt_provider,
            model=self.stt_model,
            language=self.stt_language,
        )
    
    @property
    def tts_settings(self) -> ProviderSettings:
        """Get TTS provider settings as a structured object"""
        return ProviderSettings(
            provider=self.tts_provider,
            model=self.tts_model,
            voice=self.tts_voice,
        )
    
    def validate(self) -> bool:
        """
        Validate that all required API keys are present for configured providers.
        Returns True if valid, raises ValueError if not.
        """
        errors = []
        
        # Validate LLM provider API key
        llm_key_map = {
            "openai": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "azure_openai": "AZURE_OPENAI_API_KEY",
            "together": "TOGETHER_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "qwen": "QWEN_API_KEY",
        }
        
        if self.llm_provider in llm_key_map:
            key = llm_key_map[self.llm_provider]
            if not os.getenv(key):
                errors.append(f"LLM provider '{self.llm_provider}' requires {key}")
        
        # Validate STT provider API key
        stt_key_map = {
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY",
            "deepgram": "DEEPGRAM_API_KEY",
            "assemblyai": "ASSEMBLYAI_API_KEY",
            "azure": "AZURE_SPEECH_KEY",
        }
        
        if self.stt_provider in stt_key_map:
            key = stt_key_map[self.stt_provider]
            if not os.getenv(key):
                errors.append(f"STT provider '{self.stt_provider}' requires {key}")
        
        # Validate TTS provider API key
        tts_key_map = {
            "elevenlabs": "ELEVENLABS_API_KEY",
            "cartesia": "CARTESIA_API_KEY",
            "deepgram": "DEEPGRAM_API_KEY",
            "openai": "OPENAI_API_KEY",
            "azure": "AZURE_SPEECH_KEY",
            "groq": "GROQ_API_KEY",
        }
        
        if self.tts_provider in tts_key_map:
            key = tts_key_map[self.tts_provider]
            if not os.getenv(key):
                errors.append(f"TTS provider '{self.tts_provider}' requires {key}")
        
        if errors:
            error_msg = "\n".join(f"  ❌ {e}" for e in errors)
            raise ValueError(f"Configuration validation failed:\n{error_msg}")
        
        return True
    
    def print_summary(self) -> None:
        """Print a summary of the current configuration"""
        print("\n" + "=" * 50)
        print("🎛️  LIVEKIT AGENT CONFIGURATION")
        print("=" * 50)
        
        print("\n📝 User Settings:")
        print(f"   User Name: {self.user_name}")
        
        print("\n🤖 LLM Provider:")
        print(f"   Provider: {self.llm_provider}")
        print(f"   Model: {self.llm_model or '(default)'}")
        print(f"   Temperature: {self.llm_temperature}")
        
        print("\n🎙️ STT Provider:")
        print(f"   Provider: {self.stt_provider}")
        print(f"   Model: {self.stt_model or '(default)'}")
        print(f"   Language: {self.stt_language}")
        
        print("\n🔊 TTS Provider:")
        print(f"   Provider: {self.tts_provider}")
        print(f"   Model: {self.tts_model or '(default)'}")
        print(f"   Voice: {self.tts_voice or '(default)'}")
        
        print("\n💾 Memory:")
        print(f"   Mem0 Enabled: {'✅' if self.mem0_enabled else '❌'}")
        
        print("\n🔌 MCP:")
        print(f"   N8N Server: {self.n8n_mcp_server_url or '(not configured)'}")
        
        print("\n" + "=" * 50 + "\n")

    @classmethod
    def from_env(cls) -> 'Settings':
        """Create settings from environment variables (factory method)"""
        return cls()
    
    @classmethod
    def with_overrides(cls, **overrides) -> 'Settings':
        """
        Create settings with specific overrides.
        Useful for testing or runtime configuration.
        
        Example:
            settings = Settings.with_overrides(
                llm_provider="openai",
                llm_model="gpt-4o"
            )
        """
        base = cls()
        for key, value in overrides.items():
            if hasattr(base, key):
                setattr(base, key, value)
            else:
                logger.warning(f"Unknown setting: {key}")
        return base


# Global settings instance
settings = Settings.from_env()


def reload_settings() -> Settings:
    """Reload settings from environment (useful after .env changes)"""
    global settings
    load_dotenv(override=True)
    settings = Settings.from_env()
    logger.info("🔄 Settings reloaded from environment")
    return settings


if __name__ == "__main__":
    # Print configuration summary when run directly
    settings.print_summary()
    
    try:
        settings.validate()
        print("✅ Configuration is valid!")
    except ValueError as e:
        print(f"\n{e}")
