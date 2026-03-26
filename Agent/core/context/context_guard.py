import logging
from typing import List, Dict, Any, Optional
import os

from core.context.rolling_summary import RollingSummarizer

logger = logging.getLogger(__name__)

class ContextGuard:
    def __init__(self, token_limit: Optional[int] = None, duplication_threshold: float = 0.9):
        if token_limit is None:
            self.token_limit = int(os.getenv("MAX_CONTEXT_TOKENS", "12000"))
        else:
            self.token_limit = int(token_limit)
        # Hard limit is a safety valve - never trim, just log CRITICAL.
        self.context_hard_limit = int(os.getenv("CONTEXT_HARD_LIMIT", str(self.token_limit)))
        self.max_protected_tokens = int(
            os.getenv("MAX_PROTECTED_TOKENS", os.getenv("CONTEXT_TIER1_TOKENS", "3000"))
        )
        self.max_history_tokens = int(
            os.getenv("MAX_HISTORY_TOKENS", os.getenv("CONTEXT_TIER2_TOKENS", "4000"))
        )
        self.max_memory_tokens = int(
            os.getenv("MAX_MEMORY_TOKENS", os.getenv("CONTEXT_TIER4_TOKENS", "2000"))
        )
        self.max_system_tokens = int(os.getenv("MAX_SYSTEM_TOKENS", "1500"))
        default_summary_budget = self.token_limit - (
            self.max_system_tokens + self.max_memory_tokens + self.max_history_tokens
        )
        self.max_summary_tokens = int(
            os.getenv(
                "MAX_SUMMARY_TOKENS",
                os.getenv(
                    "CONTEXT_TIER3_TOKENS",
                    str(max(300, min(3000, default_summary_budget))),
                ),
            )
        )
        self.duplication_threshold = duplication_threshold
        self.tier2_recent_turns = int(os.getenv("CONTEXT_TIER2_RECENT_TURNS", "5"))
        self.tier2_long_turn_tokens = int(os.getenv("CONTEXT_TIER2_LONG_TURN_TOKENS", "1500"))
        self.tier3_summarize_min_tokens = int(os.getenv("CONTEXT_TIER3_SUMMARIZE_MIN_TOKENS", "500"))
        self.rolling_summarizer = RollingSummarizer()
        try:
            import tiktoken
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            self.encoder = None
            logger.warning(
                "tiktoken unavailable, using character count approximation: %s", e
            )

    @staticmethod
    def _normalize_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    if isinstance(item.get("text"), str):
                        parts.append(item["text"])
                elif hasattr(item, "text"):
                    parts.append(str(getattr(item, "text")))
                else:
                    parts.append(str(item))
            return " ".join([p for p in parts if p]).strip()
        return str(content)

    def _extract_message(self, message: Any) -> Dict[str, Any]:
        if isinstance(message, dict):
            role = str(message.get("role", "user"))
            content = self._normalize_content(message.get("content", ""))
            source = str(message.get("source", "history"))
            extracted = {"role": role, "content": content, "source": source}
            for key in ("score", "similarity", "relevance_score", "metadata", "protected", "type"):
                if key in message:
                    extracted[key] = message[key]
            return extracted

        role = str(getattr(message, "role", "user"))
        content = self._normalize_content(getattr(message, "content", ""))
        source = str(getattr(message, "source", "history"))
        return {"role": role, "content": content, "source": source}

    def _messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        return sum(self.count_tokens(str(m.get("content", ""))) for m in messages)

    def _normalize_source(self, message: Dict[str, Any]) -> str:
        return str(message.get("source", "history") or "history").strip().lower()

    def _is_tier1_protected(self, message: Dict[str, Any]) -> bool:
        source = self._normalize_source(message)
        message_type = str(message.get("type", "") or "").strip().lower()
        if bool(message.get("protected", False)):
            return True
        if message_type in {"task_state", "task_step", "tool_output", "user_intent"}:
            return True
        return source in {"task_state", "task_step", "tool_output", "user_intent"}

    def _extract_score(self, message: Dict[str, Any]) -> float:
        for key in ("score", "similarity", "relevance_score"):
            value = message.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        metadata = message.get("metadata")
        if isinstance(metadata, dict):
            for key in ("score", "similarity", "relevance_score"):
                value = metadata.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
        return 0.0

    def _truncate_to_tokens(self, content: str, max_tokens: int, suffix: str = " [truncated]") -> str:
        if max_tokens <= 0:
            return suffix.strip()
        if self.count_tokens(content) <= max_tokens:
            return content
        if self.encoder:
            encoded = self.encoder.encode(content)
            suffix_tokens = self.count_tokens(suffix) if suffix else 0
            trimmed_tokens = encoded[: max(1, max_tokens - suffix_tokens)]
            return self.encoder.decode(trimmed_tokens).rstrip() + suffix
        approx_chars = max(1, max_tokens * 4)
        body = content[:approx_chars].rstrip()
        return body + suffix

    def _prepare_tier2_recent(self, messages: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], bool]:
        if self.tier2_recent_turns <= 0:
            return [], bool(messages)
        recent = list(messages[-self.tier2_recent_turns:])
        tier2_trimmed = len(messages) > len(recent)
        for msg in recent:
            content = str(msg.get("content", ""))
            tokens = self.count_tokens(content)
            if tokens > self.tier2_long_turn_tokens:
                logger.warning(
                    "context_guard_tier2_long_turn turn_tokens=%s max_tokens=%s",
                    tokens,
                    self.tier2_long_turn_tokens,
                )
                msg["content"] = self._truncate_to_tokens(content, self.tier2_long_turn_tokens)
                tier2_trimmed = True
        return recent, tier2_trimmed

    def _summarize_tier3(self, older_messages: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], bool]:
        if not older_messages:
            return [], False
        if self._messages_tokens(older_messages) < self.tier3_summarize_min_tokens:
            return list(older_messages), False

        try:
            summary_text = self.rolling_summarizer.summarize_sync(
                older_messages, token_budget=self.max_summary_tokens
            )
            summary_text = (summary_text or "").strip()
            if not summary_text:
                raise ValueError("empty_summary")
            summary_text = self._truncate_to_tokens(summary_text, self.max_summary_tokens, suffix="")
            return [
                {
                    "role": "assistant",
                    "content": summary_text,
                    "source": "history_summary",
                }
            ], True
        except Exception as exc:
            logger.warning("context_guard_tier3_summarizer_fallback reason=%s", str(exc))
            return list(older_messages[-3:]), True

    def _trim_tier4_memory(self, memory_messages: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], bool]:
        trimmed = list(memory_messages)
        dropped = 0
        while trimmed and self._messages_tokens(trimmed) > self.max_memory_tokens:
            lowest_index = min(range(len(trimmed)), key=lambda idx: self._extract_score(trimmed[idx]))
            trimmed.pop(lowest_index)
            dropped += 1
        if dropped:
            logger.info("context_guard_tier4_trimmed dropped=%s", dropped)
        return trimmed, dropped > 0

    def enforce(self, messages: List[Any], origin: str = "chat") -> List[Dict[str, Any]]:
        """
        Enforce tiered context budgets:
        Tier 1 (protected): task/tool/intent content (never truncated).
        Tier 2 (recent): recent verbatim history (last N by count).
        Tier 3 (summarized): compressed older history.
        Tier 4 (semantic): scored memory snippets.
        """
        normalized = [self._extract_message(m) for m in messages if m is not None]
        if not normalized:
            return [{"role": "system", "content": "You are a helpful assistant.", "source": "system_prompt"}]

        system_prompt: Dict[str, Any] = {
            "role": "system",
            "content": "You are a helpful assistant.",
            "source": "system_prompt",
        }
        tier1_protected: List[Dict[str, Any]] = []
        tier2_pool: List[Dict[str, Any]] = []
        tier3_seed: List[Dict[str, Any]] = []
        tier4_memory: List[Dict[str, Any]] = []
        current_user: Optional[Dict[str, Any]] = None

        for message in normalized:
            source = self._normalize_source(message)
            if source == "system_prompt":
                system_prompt = message
            elif source == "current_user":
                current_user = message
            elif self._is_tier1_protected(message):
                tier1_protected.append(message)
            elif source == "memory":
                tier4_memory.append(message)
            elif source == "history_summary":
                tier3_seed.append(message)
            else:
                tier2_pool.append(message)

        if current_user is None:
            for idx in range(len(tier2_pool) - 1, -1, -1):
                if tier2_pool[idx].get("role") == "user":
                    current_user = tier2_pool.pop(idx)
                    break

        system_tokens = self.count_tokens(system_prompt.get("content", ""))
        protected_tokens = self._messages_tokens(tier1_protected)
        if protected_tokens >= self.max_protected_tokens:
            # Keep legacy and new log keys for compatibility with existing tests/dashboards.
            logger.warning(
                "context_guard_protected_over_budget tokens=%s max_protected_tokens=%s",
                protected_tokens,
                self.max_protected_tokens,
            )
            logger.warning(
                "context_guard_tier1_overflow tokens=%s max_protected_tokens=%s",
                protected_tokens,
                self.max_protected_tokens,
            )

        # Tier 2 selection by count happens before Tier 3 summary build.
        tier2_recent, history_trimmed = self._prepare_tier2_recent(tier2_pool)
        older_history = tier3_seed + tier2_pool[: max(0, len(tier2_pool) - len(tier2_recent))]
        tier3_summary, summary_trimmed = self._summarize_tier3(older_history)
        tier4_memory, memory_trimmed = self._trim_tier4_memory(tier4_memory)

        def _assemble() -> List[Dict[str, Any]]:
            assembled_msgs: List[Dict[str, Any]] = [system_prompt]
            assembled_msgs.extend(tier1_protected)
            assembled_msgs.extend(tier3_summary)
            assembled_msgs.extend(tier2_recent)
            assembled_msgs.extend(tier4_memory)
            if current_user is not None:
                assembled_msgs.append(current_user)
            return assembled_msgs

        assembled = _assemble()
        total_tokens = self._messages_tokens(assembled)
        truncation_source = "none"
        if memory_trimmed:
            truncation_source = "memory"
        elif summary_trimmed:
            truncation_source = "summary"
        elif history_trimmed:
            truncation_source = "history"
        truncated = memory_trimmed or summary_trimmed or history_trimmed

        if total_tokens > self.context_hard_limit:
            logger.critical(
                "context_guard_hard_limit_reached total_tokens=%s hard_limit=%s "
                "ACTION_REQUIRED=review_tier_budgets_and_increase_limits",
                total_tokens,
                self.context_hard_limit,
            )

        if system_tokens > self.max_system_tokens:
            logger.warning(
                "context_guard_system_prompt_over_budget tokens=%s max_system_tokens=%s",
                system_tokens,
                self.max_system_tokens,
            )

        logger.info(
            "context_guard_enforced origin=%s context_guard_tokens_total=%s "
            "context_guard_tokens_protected=%s context_guard_tokens_memory=%s "
            "context_guard_tokens_history=%s context_guard_truncated=%s "
            "context_guard_truncation_source=%s",
            origin,
            total_tokens,
            protected_tokens,
            self._messages_tokens(tier4_memory),
            self._messages_tokens(tier2_recent + tier3_summary),
            truncated,
            truncation_source,
        )

        return assembled

    def count_tokens(self, text: str) -> int:
        if self.encoder:
            return len(self.encoder.encode(text))
        return len(text) // 4  # Rough approximation

    def guard_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ensure history fits within token limit.
        Truncates oldest messages if necessary, keeping system prompt.
        """
        if not history:
            return []

        # Identify system message (usually first) to preserve it
        system_ws = []
        chat_ws = []

        for msg in history:
            if msg.get("role") == "system":
                system_ws.append(msg)
            else:
                chat_ws.append(msg)

        total_tokens = sum(
            self.count_tokens(str(m.get("content", ""))) for m in (system_ws + chat_ws)
        )

        if total_tokens <= self.token_limit:
            return history

        logger.info(f"History usage {total_tokens} > {self.token_limit}. Truncating...")

        # Simple truncation strategy: Drop oldest chat messages until fit
        while total_tokens > self.token_limit and chat_ws:
            removed = chat_ws.pop(0)
            removed_tokens = self.count_tokens(str(removed.get("content", "")))
            total_tokens -= removed_tokens

        return system_ws + chat_ws

    def truncate_tool_output(self, content: str, max_tokens: int = 1000) -> str:
        """Truncate large tool outputs."""
        tokens = self.count_tokens(content)
        if tokens <= max_tokens:
            return content
            
        logger.info(f"Truncating tool output from {tokens} to {max_tokens} tokens")
        
        if self.encoder:
            encoded = self.encoder.encode(content)
            truncated = encoded[:max_tokens]
            return self.encoder.decode(truncated) + "\n... [Output Truncated]"
        else:
            # Approx 4 chars per token
            limit_chars = max_tokens * 4
            return content[:limit_chars] + "\n... [Output Truncated]"
    def check_tool_loops(self, history: List[Dict[str, Any]], threshold: int = 3) -> Optional[str]:
        """Check for repeated tool execution loops."""
        consecutive_count = 0
        last_tool_sig = None
        
        # Iterate backwards
        for msg in reversed(history):
            if msg.get("role") != "assistant":
                continue
                
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                # If assistant message has no tools, loop might be broken or it's just chatter.
                # If we want to be strict about consecutive TOOLS, we reset count if we see non-tool assistant msg?
                # Or we skip text-only? 
                # Usually loop is: Call Tool -> Result -> Call Tool -> Result.
                continue
                
            # Check only the first tool for simplicity, or all.
            # Convert tool calls to string signature for comparison
            # tool_calls is likely list of objects or dicts.
            # In serialized dict, it's list of objects (livekit ToolCall) or dicts.
            # We assume objects if not converted.
            
            # SmartLLM passes the object directly in serialized dict (see previous step).
            # So here we compare str(tool_calls).
            
            current_sig = str(tool_calls)
            
            if current_sig == last_tool_sig:
                consecutive_count += 1
            else:
                last_tool_sig = current_sig
                consecutive_count = 1
                
            if consecutive_count >= threshold:
                return f"Tool loop detected: {last_tool_sig}"
                
        return None
