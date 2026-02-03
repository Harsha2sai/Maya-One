"""
LLM Provider Factory Module
Supports multiple LLM providers with dynamic selection at runtime.
All API keys are loaded from environment variables.

Supported Providers:
- OpenAI (GPT-4, GPT-4o, etc.)
- Groq (Llama 3, Gemma, etc.)
- Google Gemini
- Anthropic (Claude)
- Azure OpenAI
- AWS Bedrock
- Together.ai
- Mistral
- Perplexity
- Ollama (local)
- vLLM (local server)
- DeepSeek
- Qwen
"""

import os
import logging
import threading
from typing import Any, Optional, Dict

from .provider_types import LLMProvider, LLM_DEFAULTS

logger = logging.getLogger(__name__)

# Cache for LLM instance (with thread-safe lock)
_llm_cache: Optional[Any] = None
_cache_key: Optional[str] = None
_cache_lock = threading.Lock()


def get_llm_provider(
    provider_name: str,
    model: str = "",
    temperature: float = 0.7,
    **kwargs
) -> Any:
    """
    Factory function to get an LLM provider instance.
    
    Args:
        provider_name: Name of the provider (e.g., "openai", "groq", "gemini")
        model: Model name to use (provider-specific, uses default if empty)
        temperature: Temperature for generation (0.0-1.0)
        **kwargs: Additional provider-specific arguments
    
    Returns:
        LiveKit-compatible LLM instance
    
    Raises:
        ValueError: If provider is not supported or API key is missing
    
    Example:
        >>> llm = get_llm_provider("groq", model="llama3-70b-8192")
        >>> llm = get_llm_provider("openai", model="gpt-4o", temperature=0.5)
    """
    provider = provider_name.lower().strip()
    
    logger.info(f"🤖 Initializing LLM provider: {provider}")
    
    try:
        match provider:
            case "openai":
                return _get_openai_llm(model, temperature, **kwargs)
            case "groq":
                return _get_groq_llm(model, temperature, **kwargs)
            case "gemini" | "google":
                return _get_gemini_llm(model, temperature, **kwargs)
            case "anthropic" | "claude":
                return _get_anthropic_llm(model, temperature, **kwargs)
            case "azure_openai" | "azure-openai" | "azureopenai":
                return _get_azure_openai_llm(model, temperature, **kwargs)
            case "aws_bedrock" | "bedrock" | "aws":
                return _get_bedrock_llm(model, temperature, **kwargs)
            case "together" | "together_ai" | "togetherai":
                return _get_together_llm(model, temperature, **kwargs)
            case "mistral":
                return _get_mistral_llm(model, temperature, **kwargs)
            case "perplexity":
                return _get_perplexity_llm(model, temperature, **kwargs)
            case "ollama":
                return _get_ollama_llm(model, temperature, **kwargs)
            case "vllm":
                return _get_vllm_llm(model, temperature, **kwargs)
            case "deepseek":
                return _get_deepseek_llm(model, temperature, **kwargs)
            case "qwen":
                return _get_qwen_llm(model, temperature, **kwargs)
            case _:
                raise ValueError(
                    f"❌ Unsupported LLM provider: '{provider}'. "
                    f"Supported providers: {[p.value for p in LLMProvider]}"
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


def get_llm_instance() -> Any:
    """
    Returns the LLM instance based on environment configuration.
    Implements caching to avoid repeated initialization.
    
    This is a backward-compatible wrapper around get_llm_provider()
    that reads configuration from environment variables.
    
    Environment Variables:
    - LLM_PROVIDER: Provider to use (default: "groq")
    - LLM_MODEL: Model name to use (provider-specific)
    - LLM_TEMPERATURE: Temperature for generation (default: 0.7)
    
    Returns:
        LiveKit-compatible LLM instance
    """
    global _llm_cache, _cache_key
    
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    model = os.getenv("LLM_MODEL", "")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    current_key = f"{provider}:{model}:{temperature}"
    
    # Thread-safe cache check
    with _cache_lock:
        if _llm_cache is not None and _cache_key == current_key:
            logger.debug(f"📦 Using cached LLM instance: {provider}")
            return _llm_cache
    
    try:
        llm = get_llm_provider(provider, model, temperature)
        
        # Thread-safe cache update
        with _cache_lock:
            _llm_cache = llm
            _cache_key = current_key
        
        return llm
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize {provider}: {type(e).__name__}: {e}")
        
        # Check if fallback is allowed
        fallback_enabled = os.getenv("FALLBACK_TO_GROQ", "false").lower() in ("true", "1", "yes")
        
        if not fallback_enabled:
            logger.error(
                "💡 To enable automatic fallback to Groq on errors, set: FALLBACK_TO_GROQ=true"
            )
            raise  # Re-raise the original exception
        
        # Fallback to Groq
        logger.warning(
            f"⚠️ Falling back to Groq provider due to {type(e).__name__}. "
            "Set FALLBACK_TO_GROQ=false to disable this behavior."
        )
        
        # Validate Groq API key before attempting fallback
        if not os.getenv("GROQ_API_KEY"):
            logger.error(
                "❌ Fallback failed: GROQ_API_KEY not found in environment. "
                "Cannot fall back to Groq. Please fix the original provider configuration."
            )
            raise  # Re-raise the original exception
        
        fallback_model = model or "llama-3.1-8b-instant"
        
        try:
            llm = _get_groq_llm(fallback_model, temperature)
            logger.info(f"✅ Successfully fell back to Groq with model: {fallback_model}")
            
            with _cache_lock:
                _llm_cache = llm
                _cache_key = f"groq:{fallback_model}:{temperature}"
            
            return llm
            
        except Exception as fallback_error:
            logger.error(
                f"❌ Fallback to Groq failed: {type(fallback_error).__name__}: {fallback_error}. "
                "Both primary and fallback providers failed."
            )
            raise  # Raise the fallback error to make it visible


def _validate_api_key(env_var: str, provider_name: str) -> str:
    """Validate that an API key exists in environment"""
    api_key = os.getenv(env_var)
    if not api_key:
        raise ValueError(
            f"❌ {env_var} not found in environment. "
            f"Please set {env_var} in your .env file."
        )
    return api_key


def _get_openai_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize OpenAI LLM"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    api_key = _validate_api_key("OPENAI_API_KEY", "OpenAI")
    model_name = model or LLM_DEFAULTS[LLMProvider.OPENAI]["model"]
    
    logger.info(f"✅ Using OpenAI model: {model_name}")
    
    return openai.LLM(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
        **kwargs
    )


def _get_groq_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Groq LLM"""
    try:
        from livekit.plugins import groq
    except ImportError:
        raise ImportError(
            "Groq plugin not installed. Install with: pip install livekit-plugins-groq"
        )
    
    api_key = _validate_api_key("GROQ_API_KEY", "Groq")
    model_name = model or LLM_DEFAULTS[LLMProvider.GROQ]["model"]
    
    logger.info(f"✅ Using Groq model: {model_name}")
    
    # Groq LLM doesn't support temperature in constructor
    return groq.LLM(model=model_name)


def _get_gemini_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Google Gemini LLM"""
    try:
        from livekit.plugins import google
    except ImportError:
        raise ImportError(
            "Google plugin not installed. Install with: pip install livekit-plugins-google"
        )
    
    api_key = _validate_api_key("GEMINI_API_KEY", "Gemini")
    model_name = model or LLM_DEFAULTS[LLMProvider.GEMINI]["model"]
    
    logger.info(f"✅ Using Gemini model: {model_name}")
    
    return google.LLM(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
        **kwargs
    )


def _get_anthropic_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Anthropic Claude LLM"""
    try:
        from livekit.plugins import anthropic
    except ImportError:
        raise ImportError(
            "Anthropic plugin not installed. Install with: pip install livekit-plugins-anthropic"
        )
    
    api_key = _validate_api_key("ANTHROPIC_API_KEY", "Anthropic")
    model_name = model or LLM_DEFAULTS[LLMProvider.ANTHROPIC]["model"]
    
    logger.info(f"✅ Using Anthropic model: {model_name}")
    
    return anthropic.LLM(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
        **kwargs
    )


def _get_azure_openai_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Azure OpenAI LLM"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    api_key = _validate_api_key("AZURE_OPENAI_API_KEY", "Azure OpenAI")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", model or "gpt-4o")
    
    if not endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT not found in environment")
    
    logger.info(f"✅ Using Azure OpenAI deployment: {deployment}")
    
    return openai.LLM.with_azure(
        model=deployment,
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        temperature=temperature,
        **kwargs
    )


def _get_bedrock_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize AWS Bedrock LLM"""
    try:
        from livekit.plugins import aws
    except ImportError:
        raise ImportError(
            "AWS plugin not installed. Install with: pip install livekit-plugins-aws"
        )
    
    _validate_api_key("AWS_ACCESS_KEY_ID", "AWS")
    _validate_api_key("AWS_SECRET_ACCESS_KEY", "AWS")
    
    region = os.getenv("AWS_REGION", "us-east-1")
    model_name = model or LLM_DEFAULTS[LLMProvider.AWS_BEDROCK]["model"]
    
    logger.info(f"✅ Using AWS Bedrock model: {model_name}")
    
    return aws.LLM(
        model=model_name,
        region=region,
        **kwargs
    )


def _get_together_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Together.ai LLM (uses OpenAI-compatible API)"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    api_key = _validate_api_key("TOGETHER_API_KEY", "Together.ai")
    model_name = model or LLM_DEFAULTS[LLMProvider.TOGETHER]["model"]
    base_url = os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1")
    
    logger.info(f"✅ Using Together.ai model: {model_name}")
    
    return openai.LLM(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        **kwargs
    )


def _get_mistral_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Mistral LLM (uses OpenAI-compatible API)"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    api_key = _validate_api_key("MISTRAL_API_KEY", "Mistral")
    model_name = model or LLM_DEFAULTS[LLMProvider.MISTRAL]["model"]
    base_url = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
    
    logger.info(f"✅ Using Mistral model: {model_name}")
    
    return openai.LLM(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        **kwargs
    )


def _get_perplexity_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Perplexity LLM (uses OpenAI-compatible API)"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    api_key = _validate_api_key("PERPLEXITY_API_KEY", "Perplexity")
    model_name = model or LLM_DEFAULTS[LLMProvider.PERPLEXITY]["model"]
    base_url = os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai")
    
    logger.info(f"✅ Using Perplexity model: {model_name}")
    
    return openai.LLM(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        **kwargs
    )


def _get_ollama_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Ollama LLM (local, uses OpenAI-compatible API)"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    model_name = model or LLM_DEFAULTS[LLMProvider.OLLAMA]["model"]
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    
    logger.info(f"✅ Using Ollama model: {model_name} (local)")
    
    return openai.LLM(
        model=model_name,
        api_key="ollama",  # Ollama doesn't need a real key
        base_url=base_url,
        temperature=temperature,
        **kwargs
    )


def _get_vllm_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize vLLM LLM (local server, uses OpenAI-compatible API)"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    model_name = model or LLM_DEFAULTS[LLMProvider.VLLM]["model"]
    base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
    
    logger.info(f"✅ Using vLLM model: {model_name} (local server)")
    
    return openai.LLM(
        model=model_name,
        api_key="vllm",  # vLLM doesn't need a real key
        base_url=base_url,
        temperature=temperature,
        **kwargs
    )


def _get_deepseek_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize DeepSeek LLM (uses OpenAI-compatible API)"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    api_key = _validate_api_key("DEEPSEEK_API_KEY", "DeepSeek")
    model_name = model or LLM_DEFAULTS[LLMProvider.DEEPSEEK]["model"]
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    
    logger.info(f"✅ Using DeepSeek model: {model_name}")
    
    return openai.LLM(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        **kwargs
    )


def _get_qwen_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Qwen LLM (uses OpenAI-compatible API)"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    api_key = _validate_api_key("QWEN_API_KEY", "Qwen")
    model_name = model or LLM_DEFAULTS[LLMProvider.QWEN]["model"]
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    logger.info(f"✅ Using Qwen model: {model_name}")
    
    return openai.LLM(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        **kwargs
    )


# Provider information for documentation
PROVIDER_INFO: Dict[str, Dict] = {
    "openai": {
        "name": "OpenAI",
        "default_model": LLM_DEFAULTS[LLMProvider.OPENAI]["model"],
        "env_vars": ["OPENAI_API_KEY"],
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "plugin": "livekit-plugins-openai",
    },
    "groq": {
        "name": "Groq",
        "default_model": LLM_DEFAULTS[LLMProvider.GROQ]["model"],
        "env_vars": ["GROQ_API_KEY"],
        "models": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "gemma2-9b-it", "mixtral-8x7b-32768"],
        "plugin": "livekit-plugins-groq",
    },
    "gemini": {
        "name": "Google Gemini",
        "default_model": LLM_DEFAULTS[LLMProvider.GEMINI]["model"],
        "env_vars": ["GEMINI_API_KEY"],
        "models": ["gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash"],
        "plugin": "livekit-plugins-google",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "default_model": LLM_DEFAULTS[LLMProvider.ANTHROPIC]["model"],
        "env_vars": ["ANTHROPIC_API_KEY"],
        "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
        "plugin": "livekit-plugins-anthropic",
    },
    "azure_openai": {
        "name": "Azure OpenAI",
        "default_model": LLM_DEFAULTS[LLMProvider.AZURE_OPENAI]["model"],
        "env_vars": ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"],
        "models": ["gpt-4o", "gpt-4", "gpt-35-turbo"],
        "plugin": "livekit-plugins-openai",
    },
    "aws_bedrock": {
        "name": "AWS Bedrock",
        "default_model": LLM_DEFAULTS[LLMProvider.AWS_BEDROCK]["model"],
        "env_vars": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"],
        "models": ["anthropic.claude-3-sonnet-20240229-v1:0", "amazon.titan-text-lite-v1"],
        "plugin": "livekit-plugins-aws",
    },
    "together": {
        "name": "Together.ai",
        "default_model": LLM_DEFAULTS[LLMProvider.TOGETHER]["model"],
        "env_vars": ["TOGETHER_API_KEY"],
        "models": ["meta-llama/Llama-3-70b-chat-hf", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
        "plugin": "livekit-plugins-openai",
    },
    "mistral": {
        "name": "Mistral AI",
        "default_model": LLM_DEFAULTS[LLMProvider.MISTRAL]["model"],
        "env_vars": ["MISTRAL_API_KEY"],
        "models": ["mistral-large-latest", "mistral-medium", "mistral-small"],
        "plugin": "livekit-plugins-openai",
    },
    "perplexity": {
        "name": "Perplexity AI",
        "default_model": LLM_DEFAULTS[LLMProvider.PERPLEXITY]["model"],
        "env_vars": ["PERPLEXITY_API_KEY"],
        "models": ["llama-3.1-sonar-large-128k-online", "llama-3.1-sonar-small-128k-online"],
        "plugin": "livekit-plugins-openai",
    },
    "ollama": {
        "name": "Ollama (Local)",
        "default_model": LLM_DEFAULTS[LLMProvider.OLLAMA]["model"],
        "env_vars": ["OLLAMA_BASE_URL"],
        "models": ["llama3", "mistral", "codellama"],
        "plugin": "livekit-plugins-openai",
    },
    "vllm": {
        "name": "vLLM (Local Server)",
        "default_model": LLM_DEFAULTS[LLMProvider.VLLM]["model"],
        "env_vars": ["VLLM_BASE_URL"],
        "models": ["meta-llama/Llama-3-8b-chat-hf"],
        "plugin": "livekit-plugins-openai",
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_model": LLM_DEFAULTS[LLMProvider.DEEPSEEK]["model"],
        "env_vars": ["DEEPSEEK_API_KEY"],
        "models": ["deepseek-chat", "deepseek-coder"],
        "plugin": "livekit-plugins-openai",
    },
    "qwen": {
        "name": "Qwen (Alibaba)",
        "default_model": LLM_DEFAULTS[LLMProvider.QWEN]["model"],
        "env_vars": ["QWEN_API_KEY"],
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
        "plugin": "livekit-plugins-openai",
    },
}


def list_llm_providers() -> None:
    """Print information about all available LLM providers"""
    print("\n🤖 Available LLM Providers:\n")
    for provider_id, info in PROVIDER_INFO.items():
        print(f"  {provider_id.upper()}")
        print(f"    Name: {info['name']}")
        print(f"    Default Model: {info['default_model']}")
        print(f"    Available Models: {', '.join(info['models'])}")
        print(f"    Required Env Vars: {', '.join(info['env_vars'])}")
        print(f"    Plugin: {info['plugin']}")
        print()


if __name__ == "__main__":
    list_llm_providers()
