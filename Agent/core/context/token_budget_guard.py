import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Explicit per-model overrides (most authoritative)
# Key: exact model string used in API calls
# ─────────────────────────────────────────────────────────────────────────────
MODEL_CONTEXT_OVERRIDES: Dict[str, int] = {
    # Groq (Llama & Mixtral)
    "llama-3.1-8b-instant":       128_000,
    "llama-3.3-70b-versatile":    128_000,
    "llama-3.2-1b-preview":       128_000,
    "llama-3.2-3b-preview":       128_000,
    "llama-3.2-11b-vision-preview": 128_000,
    "llama-3.2-90b-vision-preview": 128_000,
    "mixtral-8x7b-32768":          32_768,
    "gemma-7b-it":                  8_192,
    "gemma2-9b-it":                 8_192,

    # OpenAI
    "gpt-4o":                     128_000,
    "gpt-4o-mini":                128_000,
    "gpt-4-turbo":                128_000,
    "gpt-4":                        8_192,
    "gpt-3.5-turbo":               16_385,

    # Anthropic Claude
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-opus-20240229":     200_000,
    "claude-3-sonnet-20240229":   200_000,
    "claude-3-haiku-20240307":    200_000,

    # Google Gemini
    "gemini-1.5-pro":           1_000_000,
    "gemini-1.5-flash":         1_000_000,
    "gemini-pro":                  32_768,

    # DeepSeek (direct API)
    "deepseek-chat":               64_000,
    "deepseek-coder":              64_000,

    # NVIDIA NIM (OpenAI-compatible endpoint)
    "meta/llama-3.1-405b-instruct":      128_000,
    "meta/llama-3.1-70b-instruct":       128_000,
    "meta/llama-3.1-8b-instruct":        128_000,
    "mistralai/mistral-large-2-instruct": 128_000,
    "mistralai/mixtral-8x22b-instruct-v0.1": 64_000,
    "nvidia/nemotron-4-340b-instruct":      4_096,
    "google/gemma-2-27b-it":               8_192,
}

# ─────────────────────────────────────────────────────────────────────────────
# Provider-level fallback (when model string is unknown)
# ─────────────────────────────────────────────────────────────────────────────
PROVIDER_DEFAULTS: Dict[str, int] = {
    "groq":       128_000,
    "openai":     128_000,
    "nvidia":     128_000,
    "anthropic":  200_000,
    "gemini":   1_000_000,
    "deepseek":    64_000,
    "mistral":    128_000,
    "perplexity": 128_000,
    "together":   128_000,
    "qwen":       128_000,
    "vllm":        32_768,
    "ollama":      32_768,
}

# Safety margin – use only this fraction of the real limit to leave headroom
CONTEXT_SAFETY_RATIO = 0.90


def _active_provider() -> str:
    """Read active LLM provider from environment (set at agent startup)."""
    return os.getenv("LLM_PROVIDER", "groq").lower().strip()


def _active_model() -> str:
    """Read active LLM model from environment (set at agent startup)."""
    return os.getenv("LLM_MODEL", "").strip()


def get_model_context_limit(model_name: Optional[str] = None) -> int:
    """
    Return the safe token context limit for the current or given model.

    Resolution order:
      1. Explicit per-model override table
      2. Provider-level default (auto-detected from LLM_PROVIDER env var)
      3. Universal modern-model default (64 k tokens)

    Args:
        model_name: Optional model string. When None, reads from LLM_MODEL env var.

    Returns:
        Safe token limit (int) = real_limit × CONTEXT_SAFETY_RATIO
    """
    resolved_model   = (model_name or _active_model()).strip()
    resolved_provider = _active_provider()

    # 1. Per-model exact match
    if resolved_model in MODEL_CONTEXT_OVERRIDES:
        raw = MODEL_CONTEXT_OVERRIDES[resolved_model]
        logger.debug(
            "TokenBudget: model='%s' -> explicit override %d → safe %d",
            resolved_model, raw, int(raw * CONTEXT_SAFETY_RATIO)
        )
        return int(raw * CONTEXT_SAFETY_RATIO)

    # 2. Provider-level fallback
    if resolved_provider in PROVIDER_DEFAULTS:
        raw = PROVIDER_DEFAULTS[resolved_provider]
        logger.info(
            "TokenBudget: model='%s' not in overrides; using provider='%s' default %d → safe %d",
            resolved_model, resolved_provider, raw, int(raw * CONTEXT_SAFETY_RATIO)
        )
        return int(raw * CONTEXT_SAFETY_RATIO)

    # 3. Universal fallback
    default = 64_000
    logger.info(
        "TokenBudget: unknown provider='%s', model='%s'; using universal default %d → safe %d",
        resolved_provider, resolved_model, default, int(default * CONTEXT_SAFETY_RATIO)
    )
    return int(default * CONTEXT_SAFETY_RATIO)


def enforce_budget(
    messages: List[Dict[str, str]], model_name: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Enforces a dynamic token budget on conversation history.

    The budget is determined automatically from the active LLM_PROVIDER and
    LLM_MODEL env vars (or the explicit model_name argument). No global hard-
    cap is imposed; the budget adapts to whatever the user has configured.

    Strategy:
      - Preserves the system prompt (role == "system", first message).
      - Preserves the latest user message (last message).
      - Drops oldest middle messages until the budget is satisfied.

    This uses a fast char/4 heuristic (≈1 token per 4 chars) to avoid
    tokenizer overhead inside a hot chatbot loop.
    """
    if not messages:
        return messages

    effective_limit = get_model_context_limit(model_name)

    def estimate_tokens(msg: Dict[str, str]) -> int:
        return len(str(msg.get("content", ""))) // 4

    total_tokens = sum(estimate_tokens(m) for m in messages)

    if total_tokens <= effective_limit:
        return messages

    active_model    = model_name or _active_model()
    active_provider = _active_provider()
    logger.warning(
        "✂️ TokenBudget [provider=%s, model=%s]: %d tokens > %d limit — trimming history.",
        active_provider, active_model, total_tokens, effective_limit,
    )

    current = list(messages)
    while total_tokens > effective_limit and len(current) > 2:
        removed       = current.pop(1)          # drop oldest non-system message
        total_tokens -= estimate_tokens(removed)

    return current
