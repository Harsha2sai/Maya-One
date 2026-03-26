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
import re
from typing import Any, Optional, Dict, Tuple

from .provider_types import LLMProvider, LLM_DEFAULTS

# Plugins are lazy-loaded in factory functions to prevent import deadlocks
# and ensure proper initialization context.


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
            case "nvidia":
                return _get_nvidia_llm(model, temperature, **kwargs)
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
    Delegates to ProviderFactory for centralized caching.
    """
    from .factory import ProviderFactory
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    model = os.getenv("LLM_MODEL", "")
    temperature_str = os.getenv("LLM_TEMPERATURE", "0.7")
    try:
        temperature = float(temperature_str)
    except ValueError:
        temperature = 0.7
        
    return ProviderFactory.get_llm(provider, model, temperature)




def _validate_api_key(env_var: str, provider_name: str) -> str:
    """Validate that an API key exists in environment"""
    api_key = os.getenv(env_var)
    if not api_key:
        raise ValueError(
            f"❌ {env_var} not found in environment. "
            f"Please set {env_var} in your .env file."
        )
    return api_key


def _parse_preferred_slot(
    provider_prefix: str,
    key_slot: Any = None,
) -> Optional[int]:
    """Resolve preferred slot from explicit arg or <PROVIDER>_ACTIVE_KEY_SLOT env."""
    active_slot_env = os.getenv(f"{provider_prefix}_ACTIVE_KEY_SLOT", "").strip()
    preferred_slot: Optional[int] = None

    raw_value = key_slot if key_slot is not None else active_slot_env
    if raw_value is None:
        return None

    try:
        preferred_slot = int(str(raw_value).strip())
    except Exception:
        preferred_slot = None
    return preferred_slot


def _resolve_multi_slot_api_key(
    *,
    provider_prefix: str,
    provider_name: str,
    base_env_var: str,
    explicit_api_key: Optional[str] = None,
    key_slot: Any = None,
) -> Tuple[str, Optional[int]]:
    """
    Resolve API key across dynamic slots:
      SLOT 1 -> <BASE_ENV_VAR>
      SLOT N -> <BASE_ENV_VAR>_<N>
    Honors <PROVIDER>_ACTIVE_KEY_SLOT when present.
    """
    preferred_slot = _parse_preferred_slot(provider_prefix, key_slot)

    if explicit_api_key:
        return explicit_api_key, preferred_slot or 0

    key_candidates: Dict[int, str] = {}
    base_value = os.getenv(base_env_var, "").strip()
    if base_value:
        key_candidates[1] = base_value

    # Optional UI-saved slot count helps expose newly created slots immediately.
    slot_count_env = os.getenv(f"{provider_prefix}_SLOT_COUNT", "").strip()
    max_slot_from_count = 1
    try:
        if slot_count_env:
            max_slot_from_count = max(1, int(slot_count_env))
    except Exception:
        max_slot_from_count = 1

    pattern = re.compile(rf"^{re.escape(base_env_var)}_(\d+)$")
    discovered_slots = []
    for env_name, env_value in os.environ.items():
        m = pattern.match(env_name)
        if not m:
            continue
        try:
            slot_num = int(m.group(1))
        except Exception:
            continue
        candidate = str(env_value or "").strip()
        if candidate:
            key_candidates[slot_num] = candidate
            discovered_slots.append(slot_num)

    max_slot = max([1, max_slot_from_count, *discovered_slots])
    ordered_slots = list(range(1, max_slot + 1))
    if preferred_slot and preferred_slot in ordered_slots:
        ordered_slots = [preferred_slot] + [s for s in ordered_slots if s != preferred_slot]

    for slot in ordered_slots:
        candidate = key_candidates.get(slot, "").strip()
        if candidate:
            return candidate, slot

    # Fall back to required primary key validation for clear error message.
    return _validate_api_key(base_env_var, provider_name), 1


def _get_openai_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize OpenAI LLM"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)
    api_key, selected_slot = _resolve_multi_slot_api_key(
        provider_prefix="OPENAI",
        provider_name="OpenAI",
        base_env_var="OPENAI_API_KEY",
        explicit_api_key=explicit_api_key,
        key_slot=key_slot,
    )
    model_name = model or LLM_DEFAULTS[LLMProvider.OPENAI]["model"]
    
    logger.info(
        f"✅ Using OpenAI model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
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
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)

    active_slot_env = os.getenv("GROQ_ACTIVE_KEY_SLOT", "").strip()
    preferred_slot: Optional[int] = None
    if key_slot is not None:
        try:
            preferred_slot = int(key_slot)
        except Exception:
            preferred_slot = None
    elif active_slot_env:
        try:
            preferred_slot = int(active_slot_env)
        except Exception:
            preferred_slot = None

    if explicit_api_key:
        api_key = explicit_api_key
        selected_slot = preferred_slot or 0
    else:
        key_1 = os.getenv("GROQ_API_KEY", "").strip()
        key_2 = os.getenv("GROQ_API_KEY_2", "").strip()
        key_3 = os.getenv("GROQ_API_KEY_3", "").strip()
        key_candidates = {
            1: key_1,
            2: key_2,
            3: key_3,
        }
        ordered_slots = [1, 2, 3]
        if preferred_slot in (1, 2, 3):
            ordered_slots = [preferred_slot] + [s for s in ordered_slots if s != preferred_slot]

        selected_slot = None
        api_key = ""
        for slot in ordered_slots:
            candidate = key_candidates.get(slot, "")
            if candidate:
                selected_slot = slot
                api_key = candidate
                break

        if not api_key:
            api_key = _validate_api_key("GROQ_API_KEY", "Groq")
            selected_slot = 1

    model_name = model or LLM_DEFAULTS[LLMProvider.GROQ]["model"]
    
    logger.info(
        f"✅ Using Groq model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
    return groq.LLM(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
        **kwargs,
    )


def _get_gemini_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Google Gemini LLM"""
    try:
        from livekit.plugins import google
    except ImportError:
        raise ImportError(
            "Google plugin not installed. Install with: pip install livekit-plugins-google"
        )
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)

    active_slot_env = os.getenv("GEMINI_ACTIVE_KEY_SLOT", "").strip()
    preferred_slot: Optional[int] = None
    if key_slot is not None:
        try:
            preferred_slot = int(key_slot)
        except Exception:
            preferred_slot = None
    elif active_slot_env:
        try:
            preferred_slot = int(active_slot_env)
        except Exception:
            preferred_slot = None

    if explicit_api_key:
        api_key = explicit_api_key
        selected_slot = preferred_slot or 0
    else:
        oauth_1 = os.getenv("GEMINI_OAUTH_ACCESS_TOKEN", "").strip()
        oauth_2 = os.getenv("GEMINI_OAUTH_ACCESS_TOKEN_2", "").strip()
        key_1 = os.getenv("GEMINI_API_KEY", "").strip()
        key_2 = os.getenv("GEMINI_API_KEY_2", "").strip()
        
        # Prioritize OAuth over API Keys for the same slot
        key_candidates = {
            1: oauth_1 if oauth_1 else key_1,
            2: oauth_2 if oauth_2 else key_2,
        }
        
        ordered_slots = [1, 2]
        if preferred_slot in (1, 2):
            ordered_slots = [preferred_slot] + [s for s in ordered_slots if s != preferred_slot]

        selected_slot = None
        api_key = ""
        for slot in ordered_slots:
            candidate = key_candidates.get(slot, "")
            if candidate:
                selected_slot = slot
                api_key = candidate
                break

        if not api_key:
            # Fallback to standard validation (which will raise if missing)
            api_key = _validate_api_key("GEMINI_API_KEY", "Gemini")
            selected_slot = 1

    model_name = model or LLM_DEFAULTS[LLMProvider.GEMINI]["model"]
    
    logger.info(
        f"✅ Using Gemini model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
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
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)
    api_key, selected_slot = _resolve_multi_slot_api_key(
        provider_prefix="ANTHROPIC",
        provider_name="Anthropic",
        base_env_var="ANTHROPIC_API_KEY",
        explicit_api_key=explicit_api_key,
        key_slot=key_slot,
    )
    model_name = model or LLM_DEFAULTS[LLMProvider.ANTHROPIC]["model"]
    
    logger.info(
        f"✅ Using Anthropic model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
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
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)
    api_key, selected_slot = _resolve_multi_slot_api_key(
        provider_prefix="TOGETHER",
        provider_name="Together.ai",
        base_env_var="TOGETHER_API_KEY",
        explicit_api_key=explicit_api_key,
        key_slot=key_slot,
    )
    model_name = model or LLM_DEFAULTS[LLMProvider.TOGETHER]["model"]
    base_url = os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1")
    
    logger.info(
        f"✅ Using Together.ai model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
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
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)
    api_key, selected_slot = _resolve_multi_slot_api_key(
        provider_prefix="MISTRAL",
        provider_name="Mistral",
        base_env_var="MISTRAL_API_KEY",
        explicit_api_key=explicit_api_key,
        key_slot=key_slot,
    )
    model_name = model or LLM_DEFAULTS[LLMProvider.MISTRAL]["model"]
    base_url = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
    
    logger.info(
        f"✅ Using Mistral model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
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
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)
    api_key, selected_slot = _resolve_multi_slot_api_key(
        provider_prefix="PERPLEXITY",
        provider_name="Perplexity",
        base_env_var="PERPLEXITY_API_KEY",
        explicit_api_key=explicit_api_key,
        key_slot=key_slot,
    )
    model_name = model or LLM_DEFAULTS[LLMProvider.PERPLEXITY]["model"]
    base_url = os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai")
    
    logger.info(
        f"✅ Using Perplexity model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
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
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)
    api_key, selected_slot = _resolve_multi_slot_api_key(
        provider_prefix="DEEPSEEK",
        provider_name="DeepSeek",
        base_env_var="DEEPSEEK_API_KEY",
        explicit_api_key=explicit_api_key,
        key_slot=key_slot,
    )
    model_name = model or LLM_DEFAULTS[LLMProvider.DEEPSEEK]["model"]
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    
    logger.info(
        f"✅ Using DeepSeek model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
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
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)
    api_key, selected_slot = _resolve_multi_slot_api_key(
        provider_prefix="QWEN",
        provider_name="Qwen",
        base_env_var="QWEN_API_KEY",
        explicit_api_key=explicit_api_key,
        key_slot=key_slot,
    )
    model_name = model or LLM_DEFAULTS[LLMProvider.QWEN]["model"]
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    logger.info(
        f"✅ Using Qwen model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
    return openai.LLM(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        **kwargs
    )


def _get_nvidia_llm(model: str, temperature: float, **kwargs) -> Any:
    """Initialize Nvidia LLM (uses OpenAI-compatible API)"""
    try:
        from livekit.plugins import openai
    except ImportError:
        raise ImportError(
            "OpenAI plugin not installed. Install with: pip install livekit-plugins-openai"
        )
    
    explicit_api_key = kwargs.pop("api_key", None)
    key_slot = kwargs.pop("key_slot", None)
    api_key, selected_slot = _resolve_multi_slot_api_key(
        provider_prefix="NVIDIA",
        provider_name="Nvidia",
        base_env_var="NVIDIA_API_KEY",
        explicit_api_key=explicit_api_key,
        key_slot=key_slot,
    )
    model_name = model or LLM_DEFAULTS[LLMProvider.NVIDIA]["model"]
    base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    
    logger.info(
        f"✅ Using Nvidia model: {model_name}"
        + (f" (key slot {selected_slot})" if selected_slot else "")
    )
    
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
        "env_vars": ["OPENAI_API_KEY", "OPENAI_API_KEY_<N>", "OPENAI_ACTIVE_KEY_SLOT", "OPENAI_SLOT_COUNT"],
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "plugin": "livekit-plugins-openai",
        "multi_slot_runtime": True,
        "active_slot_env": "OPENAI_ACTIVE_KEY_SLOT",
        "slot_count_env": "OPENAI_SLOT_COUNT",
        "dynamic_key_pattern": "OPENAI_API_KEY_<N>",
    },
    "groq": {
        "name": "Groq",
        "default_model": LLM_DEFAULTS[LLMProvider.GROQ]["model"],
        "env_vars": ["GROQ_API_KEY", "GROQ_API_KEY_<N>", "GROQ_ACTIVE_KEY_SLOT", "GROQ_SLOT_COUNT"],
        "models": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "gemma2-9b-it", "mixtral-8x7b-32768"],
        "plugin": "livekit-plugins-groq",
        "multi_slot_runtime": True,
        "active_slot_env": "GROQ_ACTIVE_KEY_SLOT",
        "slot_count_env": "GROQ_SLOT_COUNT",
        "dynamic_key_pattern": "GROQ_API_KEY_<N>",
    },
    "gemini": {
        "name": "Google Gemini",
        "default_model": LLM_DEFAULTS[LLMProvider.GEMINI]["model"],
        "env_vars": ["GEMINI_OAUTH_ACCESS_TOKEN", "GEMINI_OAUTH_ACCESS_TOKEN_<N>", "GEMINI_OAUTH_REFRESH_TOKEN", "GEMINI_OAUTH_REFRESH_TOKEN_<N>", "GEMINI_API_KEY", "GEMINI_API_KEY_<N>", "GEMINI_ACTIVE_KEY_SLOT", "GEMINI_SLOT_COUNT"],
        "models": ["gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash"],
        "plugin": "livekit-plugins-google",
        "multi_slot_runtime": True,
        "active_slot_env": "GEMINI_ACTIVE_KEY_SLOT",
        "slot_count_env": "GEMINI_SLOT_COUNT",
        "dynamic_key_pattern": "GEMINI_API_KEY_<N>",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "default_model": LLM_DEFAULTS[LLMProvider.ANTHROPIC]["model"],
        "env_vars": ["ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_<N>", "ANTHROPIC_ACTIVE_KEY_SLOT", "ANTHROPIC_SLOT_COUNT"],
        "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
        "plugin": "livekit-plugins-anthropic",
        "multi_slot_runtime": True,
        "active_slot_env": "ANTHROPIC_ACTIVE_KEY_SLOT",
        "slot_count_env": "ANTHROPIC_SLOT_COUNT",
        "dynamic_key_pattern": "ANTHROPIC_API_KEY_<N>",
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
        "env_vars": ["TOGETHER_API_KEY", "TOGETHER_API_KEY_<N>", "TOGETHER_ACTIVE_KEY_SLOT", "TOGETHER_SLOT_COUNT"],
        "models": ["meta-llama/Llama-3-70b-chat-hf", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
        "plugin": "livekit-plugins-openai",
        "multi_slot_runtime": True,
        "active_slot_env": "TOGETHER_ACTIVE_KEY_SLOT",
        "slot_count_env": "TOGETHER_SLOT_COUNT",
        "dynamic_key_pattern": "TOGETHER_API_KEY_<N>",
    },
    "mistral": {
        "name": "Mistral AI",
        "default_model": LLM_DEFAULTS[LLMProvider.MISTRAL]["model"],
        "env_vars": ["MISTRAL_API_KEY", "MISTRAL_API_KEY_<N>", "MISTRAL_ACTIVE_KEY_SLOT", "MISTRAL_SLOT_COUNT"],
        "models": ["mistral-large-latest", "mistral-medium", "mistral-small"],
        "plugin": "livekit-plugins-openai",
        "multi_slot_runtime": True,
        "active_slot_env": "MISTRAL_ACTIVE_KEY_SLOT",
        "slot_count_env": "MISTRAL_SLOT_COUNT",
        "dynamic_key_pattern": "MISTRAL_API_KEY_<N>",
    },
    "perplexity": {
        "name": "Perplexity AI",
        "default_model": LLM_DEFAULTS[LLMProvider.PERPLEXITY]["model"],
        "env_vars": ["PERPLEXITY_API_KEY", "PERPLEXITY_API_KEY_<N>", "PERPLEXITY_ACTIVE_KEY_SLOT", "PERPLEXITY_SLOT_COUNT"],
        "models": ["llama-3.1-sonar-large-128k-online", "llama-3.1-sonar-small-128k-online"],
        "plugin": "livekit-plugins-openai",
        "multi_slot_runtime": True,
        "active_slot_env": "PERPLEXITY_ACTIVE_KEY_SLOT",
        "slot_count_env": "PERPLEXITY_SLOT_COUNT",
        "dynamic_key_pattern": "PERPLEXITY_API_KEY_<N>",
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
        "env_vars": ["DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY_<N>", "DEEPSEEK_ACTIVE_KEY_SLOT", "DEEPSEEK_SLOT_COUNT"],
        "models": ["deepseek-chat", "deepseek-coder"],
        "plugin": "livekit-plugins-openai",
        "multi_slot_runtime": True,
        "active_slot_env": "DEEPSEEK_ACTIVE_KEY_SLOT",
        "slot_count_env": "DEEPSEEK_SLOT_COUNT",
        "dynamic_key_pattern": "DEEPSEEK_API_KEY_<N>",
    },
    "qwen": {
        "name": "Qwen (Alibaba)",
        "default_model": LLM_DEFAULTS[LLMProvider.QWEN]["model"],
        "env_vars": ["QWEN_API_KEY", "QWEN_API_KEY_<N>", "QWEN_ACTIVE_KEY_SLOT", "QWEN_SLOT_COUNT"],
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
        "plugin": "livekit-plugins-openai",
        "multi_slot_runtime": True,
        "active_slot_env": "QWEN_ACTIVE_KEY_SLOT",
        "slot_count_env": "QWEN_SLOT_COUNT",
        "dynamic_key_pattern": "QWEN_API_KEY_<N>",
    },
    "nvidia": {
        "name": "Nvidia (NIM)",
        "default_model": LLM_DEFAULTS[LLMProvider.NVIDIA]["model"],
        "env_vars": ["NVIDIA_API_KEY", "NVIDIA_API_KEY_<N>", "NVIDIA_ACTIVE_KEY_SLOT", "NVIDIA_SLOT_COUNT"],
        "models": [
            "meta/llama-3.1-405b-instruct",
            "meta/llama-3.1-70b-instruct",
            "meta/llama-3.1-8b-instruct",
            "mistralai/mixtral-8x22b-instruct-v0.1",
            "mistralai/mistral-large-2-instruct",
            "nvidia/nemotron-4-340b-instruct",
            "google/gemma-2-27b-it"
        ],
        "plugin": "livekit-plugins-openai",
        "multi_slot_runtime": True,
        "active_slot_env": "NVIDIA_ACTIVE_KEY_SLOT",
        "slot_count_env": "NVIDIA_SLOT_COUNT",
        "dynamic_key_pattern": "NVIDIA_API_KEY_<N>",
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
