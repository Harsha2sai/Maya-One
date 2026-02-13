import os
import pytest

from config.settings import Settings, ProviderSettings


def test_settings_overrides_and_properties():
    overrides = {
        "user_name": "Test User",
        "llm_provider": "groq",
        "llm_model": "mixtral",
        "tts_voice": "en-US-AriaNeural",
    }
    settings = Settings.with_overrides(**overrides)

    assert settings.user_name == "Test User"
    assert settings.llm_provider == "groq"
    assert settings.llm_model == "mixtral"
    llm_settings = settings.llm_settings
    assert isinstance(llm_settings, ProviderSettings)
    assert llm_settings.provider == "groq"
    assert llm_settings.model == "mixtral"


def test_validate_raises_when_required_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    settings = Settings.with_overrides(
        llm_provider="openai",
        stt_provider="edge_tts",
        tts_provider="edge_tts",
    )

    with pytest.raises(ValueError) as exc:
        settings.validate()

    message = str(exc.value)
    assert "OPENAI_API_KEY" in message
    assert "STT" not in message
