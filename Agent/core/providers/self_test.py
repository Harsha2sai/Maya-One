import logging
import asyncio
from typing import Any

logger = logging.getLogger(__name__)

def run_provider_self_test():
    """
    Validates that all configured providers (LLM, STT, TTS) can be initialized.
    This catches lazy-loading errors at startup instead of during a live session.
    """
    from providers.factory import ProviderFactory
    from config.settings import settings
    
    logger.info("🔍 Running provider self-test...")
    
    try:
        # Test LLM
        logger.info(f"LLM: settings.llm_provider={settings.llm_provider}, model={settings.llm_model}")
        ProviderFactory.get_llm(settings.llm_provider, settings.llm_model)
        
        # Test STT
        logger.info(f"STT: {settings.stt_provider}")
        ProviderFactory.get_stt(settings.stt_provider, settings.stt_language, settings.stt_model)
        
        # Test TTS
        logger.info(f"TTS: {settings.tts_provider}")
        ProviderFactory.get_tts(settings.tts_provider, settings.tts_voice, settings.tts_model)
        
        logger.info("✅ Provider self-test passed")
    except Exception as e:
        logger.exception("❌ Provider self-test FAILED")
        # In worker mode, we might want to raise this to fail the boot
        raise RuntimeError(f"Critical provider failure during self-test: {e}")
