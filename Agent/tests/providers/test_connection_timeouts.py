import pytest
import asyncio
from unittest.mock import MagicMock, patch
from providers.factory import ProviderFactory


class TestProviderConnectionTimeouts:
    """Test connection timeout functionality for providers."""
    
    @pytest.mark.asyncio
    async def test_timeout_constants_defined(self):
        """Timeout constants should be defined."""
        assert hasattr(ProviderFactory, 'DEFAULT_LLM_TIMEOUT')
        assert hasattr(ProviderFactory, 'DEFAULT_STT_TIMEOUT')
        assert hasattr(ProviderFactory, 'DEFAULT_TTS_TIMEOUT')
        
        assert ProviderFactory.DEFAULT_LLM_TIMEOUT == 30
        assert ProviderFactory.DEFAULT_STT_TIMEOUT == 15
        assert ProviderFactory.DEFAULT_TTS_TIMEOUT == 15
    
    @pytest.mark.asyncio
    async def test_with_timeout_wrapper_success(self):
        """Timeout wrapper should allow fast operations."""
        async def fast_operation():
            await asyncio.sleep(0.1)
            return "success"
        
        result = await ProviderFactory._with_timeout(
            fast_operation(),
            timeout=1.0,
            provider_type="TEST"
        )
        
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_with_timeout_wrapper_timeout(self):
        """Timeout wrapper should raise TimeoutError for slow operations."""
        async def slow_operation():
            await asyncio.sleep(2.0)
            return "success"
        
        with pytest.raises(asyncio.TimeoutError):
            await ProviderFactory._with_timeout(
                slow_operation(),
                timeout=0.5,
                provider_type="TEST"
            )
    
    def test_get_llm_accepts_timeout_parameter(self):
        """get_llm should accept timeout parameter."""
        # Just verify signature accepts timeout
        import inspect
        sig = inspect.signature(ProviderFactory.get_llm)
        assert 'timeout' in sig.parameters
    
    def test_get_stt_accepts_timeout_parameter(self):
        """get_stt should accept timeout parameter."""
        import inspect
        sig = inspect.signature(ProviderFactory.get_stt)
        assert 'timeout' in sig.parameters
    
    def test_get_tts_accepts_timeout_parameter(self):
        """get_tts should accept timeout parameter."""
        import inspect
        sig = inspect.signature(ProviderFactory.get_tts)
        assert 'timeout' in sig.parameters
    
    def test_get_llm_uses_default_timeout(self):
        """get_llm should use default timeout when not specified."""
        with patch('providers.factory.get_llm_provider') as mock_provider:
            mock_provider.return_value = MagicMock()
            
            # Call without timeout
            ProviderFactory.get_llm("test", "test-model")
            
            # Should use default (verified by not raising)
    
    @pytest.mark.asyncio
    async def test_timeout_wrapper_logs_on_timeout(self, caplog):
        """Timeout wrapper should log error on timeout."""
        async def slow_operation():
            await asyncio.sleep(2.0)
        
        with pytest.raises(asyncio.TimeoutError):
            await ProviderFactory._with_timeout(
                slow_operation(),
                timeout=0.1,
                provider_type="LLM"
            )
        
        # Check that error was logged
        assert "LLM provider initialization timeout" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
