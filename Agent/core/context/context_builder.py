import os
import logging
import copy
import re
from typing import List, Tuple, Any, Optional
from livekit.agents.llm import ChatMessage, ChatContext
from core.context.context_guard import ContextGuard
from core.context.rolling_summary import RollingContextManager
from core.tasks.task_manager import TaskManager
from core.utils.intent_utils import normalize_intent
from core.utils.small_talk_detector import is_small_talk, classify_message_type
from core.prompts import get_maya_primary_prompt

logger = logging.getLogger(__name__)

IDENTITY_PATTERNS = (
    r"\b(what(?:'s| is)\s+your\s+name|who\s+are\s+you)\b",
)
CAPABILITY_PATTERNS = (
    r"\b(what can you do|how can you help|what are your features|your capabilities)\b",
)
FAREWELL_PATTERNS = (
    r"\b(thanks|thank you|cheers|bye|goodbye)\b",
)
VOICE_MEMORY_TOP_K_DEFAULT = 2
CHAT_MEMORY_TOP_K_DEFAULT = 4


class ContextBuilder:
    def __init__(
        self,
        llm,
        memory_manager,
        user_id: str,
        rolling_manager: Optional[RollingContextManager] = None,
        guard: Optional[ContextGuard] = None,
    ):
        self.llm = llm
        self.memory_manager = memory_manager
        self.user_id = user_id
        self.rolling_manager = rolling_manager
        self.agent = None
        self.guard = guard or ContextGuard()
        # Tasks are user-scoped, so we can initialize TaskManager here
        # We pass memory_manager as required
        self.task_manager = TaskManager(user_id=user_id, memory_manager=memory_manager)

    def set_agent(self, agent: Any):
        """Link agent to access tools (resolves circular dependency)"""
        self.agent = agent

    async def __call__(
        self,
        message: str,
        chat_ctx: ChatContext,
        **kwargs
    ) -> Tuple[List[ChatMessage], List[Any]]:
        """
        Constructs the exact list of messages for the LLM, implementing LRCS.
        Includes intent-based tool filtering to reduce context bloat.
        """

        # 1. Update Session via Rolling Manager
        if self.rolling_manager and chat_ctx:
            await self.rolling_manager.update_session(chat_ctx)

        # 2. Classify intent for tool filtering (PHASE 4: reduce bloat)
        intent = classify_message_type(message)
        is_chat = is_small_talk(message)

        # 3. Resolve Tools (Dynamic from Agent with filtering)
        all_tools = []
        if self.agent and hasattr(self.agent, '_tools'):
            all_tools = self.agent._tools
        else:
             logger.debug("ContextBuilder: No agent tools available")

        # Filter tools based on intent to reduce token usage
        if is_chat:
            tools = []  # No tools for small talk
            logger.debug(f"ContextBuilder: Chat mode - 0 tools (filtered from {len(all_tools)})")
        elif intent == "task_request":
            tools = all_tools  # All tools for task requests
            logger.debug(f"ContextBuilder: Task mode - {len(tools)} tools")
        else:
            # For general queries, limit to essential tools
            essential_keywords = ["web_search", "weather", "time", "date"]
            tools = [
                t for t in all_tools
                if any(kw in str(getattr(t, 'name', '')).lower() for kw in essential_keywords)
            ]
            if not tools:  # Fallback if no essential tools found
                tools = all_tools
            logger.debug(f"ContextBuilder: General mode - {len(tools)} tools (filtered from {len(all_tools)})")

        # 4. Build System Content (PHASE 4: Lightweight for chat mode)
        base_prompt = get_maya_primary_prompt()
        if is_chat:
            system_content = (
                f"{base_prompt}\n\n"
                "Conversation mode:\n"
                "- This turn is small talk or lightweight conversation.\n"
                "- Keep the reply especially friendly and concise.\n"
                "- Do not introduce tools or planning unless the user explicitly pivots into a task.\n"
            )
        else:
            # Full system prompt for task mode
            system_content = base_prompt
            system_content += """

CRITICAL TOOL USAGE:
- MUST use tools for actions (open, create, search, write, run)
- Never claim completion without tool execution
- Say "I don't have that capability" if no tool exists
"""
        
        # 4. Session Summary (truncated to 500 chars)
        if self.rolling_manager and self.rolling_manager.session_summary:
            summary = self.rolling_manager.session_summary[:500]
            if len(self.rolling_manager.session_summary) > 500:
                summary += "..."
            system_content += f"\n\n## Session Summary\n{summary}"

        # 5. Retrieved Memories (chat retrieval budget)
        if self.memory_manager and self.user_id:
            try:
                chat_k = max(1, int(os.getenv("CHAT_RETRIEVER_K", str(CHAT_MEMORY_TOP_K_DEFAULT))))
                memories = await self.memory_manager.get_user_context(self.user_id, k=chat_k)
                if memories:
                    system_content += f"\n\n## Retrieved Memories\n{memories}"
            except Exception as e:
                logger.warning(f"Failed to inject memories: {e}")

        # 6. Active Tasks Summary
        try:
            # TaskManager is persistent in self
            active_tasks = await self.task_manager.get_active_tasks()
            if active_tasks:
                task_summary = "\n\n## Active Tasks Summary\n"
                for t in active_tasks:
                    status_str = normalize_intent(t.status)
                    task_summary += f"- [{status_str}] {t.title} (ID: {t.id})\n"
                    if 0 <= t.current_step_index < len(t.steps):
                        t_step = t.steps[t.current_step_index]
                        step_status_str = normalize_intent(t_step.status)
                        task_summary += f"  Current Step: {t_step.description} ({step_status_str})\n"
                system_content += task_summary
        except Exception as e:
            logger.warning(f"Failed to inject active tasks: {e}")

        # 7. Construct Messages
        messages = [ChatMessage(role="system", content=[system_content])]
        
        # 8. Recent Conversation Window (reduced to 4 messages)
        recent_msgs = []
        if self.rolling_manager:
            recent_msgs = self.rolling_manager.get_recent_turns(chat_ctx)
        else:
            all_msgs = chat_ctx.messages
            if callable(all_msgs): all_msgs = all_msgs()
            # ⭐ FIX 3: Token Budget - Hard limit to last 4 messages
            recent_msgs = [m for m in all_msgs if m.role != "system"][-4:]
            
        messages.extend(recent_msgs)
        
        return messages, tools

    @staticmethod
    def _normalize_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif hasattr(item, "text"):
                    parts.append(str(getattr(item, "text")))
                else:
                    parts.append(str(item))
            return " ".join([p for p in parts if p]).strip()
        return str(content)

    @classmethod
    def _normalize_history_entry(cls, msg: Any) -> Optional[dict]:
        if msg is None:
            return None
        if isinstance(msg, dict):
            role = str(msg.get("role", "user"))
            content = cls._normalize_content(msg.get("content", ""))
            source = str(msg.get("source", "history") or "history")
            return {"role": role, "content": content, "source": source}
        role = str(getattr(msg, "role", "user"))
        content = cls._normalize_content(getattr(msg, "content", ""))
        source = str(getattr(msg, "source", "history") or "history")
        return {"role": role, "content": content, "source": source}

    @staticmethod
    def _memory_to_text(memory_results: list[Any]) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        raw_lines = 0
        for item in memory_results:
            metadata: dict[str, Any] = {}
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                maybe_meta = item.get("metadata")
                if isinstance(maybe_meta, dict):
                    metadata = maybe_meta
            else:
                text = str(getattr(item, "text", "")).strip()
                maybe_meta = getattr(item, "metadata", None)
                if isinstance(maybe_meta, dict):
                    metadata = maybe_meta
            if not text:
                continue

            source = str(metadata.get("source", "")).lower()
            candidate_lines: list[str]
            if source == "conversation":
                user_lines = [ln.strip() for ln in text.splitlines() if ln.strip().lower().startswith("user:")]
                candidate_lines = user_lines or [text]
            else:
                candidate_lines = [text]

            for line in candidate_lines:
                normalized = re.sub(r"\s+", " ", line.strip().lower())
                if not normalized:
                    continue
                raw_lines += 1
                if normalized in seen:
                    continue
                seen.add(normalized)
                lines.append(f"- {line.strip()}")
        logger.info(
            "context_builder_memory_sanitized raw_items=%s raw_lines=%s kept_lines=%s deduped_lines=%s",
            len(memory_results or []),
            raw_lines,
            len(lines),
            max(0, raw_lines - len(lines)),
        )
        return "\n".join(lines)

    @staticmethod
    def _should_skip_memory_for_query(user_message: str) -> bool:
        text = (user_message or "").strip().lower()
        if not text:
            return True
        patterns = IDENTITY_PATTERNS + CAPABILITY_PATTERNS + FAREWELL_PATTERNS
        return any(re.search(pattern, text) for pattern in patterns)

    @staticmethod
    def _limit_semantic_results(memory_results: list[Any], top_k: int) -> list[Any]:
        if top_k <= 0:
            return []
        return list(memory_results or [])[:top_k]

    @staticmethod
    def _summarize_older_history(older_history: list[dict], max_items: int = 8) -> str:
        if not older_history:
            return ""

        snippets: list[str] = []
        for msg in older_history:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            compact = re.sub(r"\s+", " ", content)
            if len(compact) > 140:
                compact = f"{compact[:137].rstrip()}..."
            snippets.append(f"- {role}: {compact}")

        if not snippets:
            return ""

        if len(snippets) > max_items:
            head = snippets[: max_items // 2]
            tail = snippets[-(max_items // 2) :]
            snippets = head + ["- ..."] + tail

        return "[Earlier conversation summary]\n" + "\n".join(snippets)

    @staticmethod
    def _partition_history(
        history: list[Any],
        recent_limit: int,
    ) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        protected: list[dict] = []
        continuity: list[dict] = []
        regular: list[dict] = []

        for msg in history:
            normalized = ContextBuilder._normalize_history_entry(msg)
            if normalized is None:
                continue
            source = str(normalized.get("source", "history") or "history")
            if normalized.get("role") == "system" and source != "session_continuity":
                continue
            if source in {"tool_output", "task_step"}:
                protected.append(normalized)
            elif source == "session_continuity":
                continuity.append(normalized)
            else:
                normalized["source"] = "history"
                regular.append(normalized)

        if recent_limit <= 0:
            return protected, regular, continuity, []

        split_index = max(0, len(regular) - recent_limit)
        older = regular[:split_index]
        recent = regular[split_index:]
        return protected, older, continuity, recent

    def _build_raw(
        self,
        system_prompt: str,
        memory_results: list[Any],
        history: list[Any],
        user_message: str,
        history_limit: int,
    ) -> list[dict]:
        raw: list[dict] = [
            {
                "role": "system",
                "content": system_prompt.strip() if system_prompt else AGENT_INSTRUCTION,
                "source": "system_prompt",
            }
        ]

        protected_history, older_history, continuity_messages, recent_history = self._partition_history(
            history,
            history_limit,
        )

        raw.extend(protected_history)

        summary_text = self._summarize_older_history(older_history)
        if summary_text:
            raw.append(
                {
                    "role": "assistant",
                    "content": summary_text,
                    "source": "history_summary",
                }
            )

        # Keep session continuity pinned at the front of Tier 2 recent context.
        raw.extend(continuity_messages)
        raw.extend(recent_history)

        memory_text = self._memory_to_text(memory_results)
        if memory_text:
            raw.append(
                {
                    "role": "user",
                    "content": f"[Memory from previous conversations:]\n{memory_text}",
                    "source": "memory",
                }
            )
            logger.debug(
                "context_builder_memory_appended_to_context chars=%s",
                len(memory_text),
            )

        raw.append(
            {
                "role": "user",
                "content": user_message or "",
                "source": "current_user",
            }
        )
        return raw

    def _assemble_and_guard(
        self,
        system_prompt: str,
        memory_results: list[dict],
        history: list[Any],
        user_message: str,
        origin: str,
        history_limit: int,
    ) -> List[ChatMessage]:
        raw_context = self._build_raw(
            system_prompt,
            memory_results,
            history,
            user_message,
            history_limit=history_limit,
        )
        guarded_context = self.guard.enforce(raw_context, origin=origin)
        messages: List[ChatMessage] = []
        for msg in guarded_context:
            role = str(msg.get("role", "user"))
            content = self._normalize_content(msg.get("content", ""))
            messages.append(ChatMessage(role=role, content=[content]))
        return messages

    async def build_for_voice(
        self,
        user_message: str,
        user_id: str | None,
        session_id: str | None,
        conversation_history: list[Any],
        system_prompt: str,
        retriever: Any,
    ) -> List[ChatMessage]:
        voice_k = max(1, int(os.getenv("VOICE_RETRIEVER_K", str(VOICE_MEMORY_TOP_K_DEFAULT))))
        memory_results: list[dict] = []
        skip_memory = self._should_skip_memory_for_query(user_message)
        if retriever is not None and not skip_memory:
            if hasattr(retriever, "retrieve_with_scope_fallback"):
                retrieval_kwargs = {
                    "query": user_message,
                    "user_id": user_id,
                    "session_id": session_id,
                    "origin": "voice",
                    "k": voice_k,
                }
                try:
                    memory_results = await retriever.retrieve_with_scope_fallback(
                        **retrieval_kwargs,
                    )
                except TypeError:
                    retrieval_kwargs.pop("k", None)
                    memory_results = await retriever.retrieve_with_scope_fallback(
                        **retrieval_kwargs,
                    )
            elif hasattr(retriever, "retrieve_async"):
                retrieval_kwargs = {
                    "query": user_message,
                    "user_id": user_id,
                    "session_id": session_id,
                    "origin": "voice",
                    "k": voice_k,
                }
                try:
                    memory_results = await retriever.retrieve_async(**retrieval_kwargs)
                except TypeError:
                    retrieval_kwargs.pop("k", None)
                    memory_results = await retriever.retrieve_async(**retrieval_kwargs)
        elif skip_memory:
            logger.info("context_builder_memory_skipped reason=identity_or_capability_or_small_talk origin=voice")

        memory_results = self._limit_semantic_results(memory_results, voice_k)
        if not skip_memory:
            if memory_results:
                logger.info(
                    "context_builder_memory_injected count=%s origin=voice",
                    len(memory_results),
                )
            else:
                logger.info(
                    "context_builder_memory_skipped reason=retrieval_empty origin=voice"
                )

        return self._assemble_and_guard(
            system_prompt=system_prompt,
            memory_results=memory_results,
            history=conversation_history,
            user_message=user_message,
            origin="voice",
            history_limit=5,
        )

    async def build_for_chat(
        self,
        user_message: str,
        user_id: str | None,
        session_id: str | None,
        conversation_history: list[Any],
        system_prompt: str,
        retriever: Any,
    ) -> List[ChatMessage]:
        chat_k = max(1, int(os.getenv("CHAT_RETRIEVER_K", str(CHAT_MEMORY_TOP_K_DEFAULT))))
        memory_results: list[dict] = []
        skip_memory = self._should_skip_memory_for_query(user_message)
        if retriever is not None and not skip_memory:
            if hasattr(retriever, "retrieve_with_scope_fallback"):
                retrieval_kwargs = {
                    "query": user_message,
                    "user_id": user_id,
                    "session_id": session_id,
                    "origin": "chat",
                    "k": chat_k,
                }
                try:
                    memory_results = await retriever.retrieve_with_scope_fallback(
                        **retrieval_kwargs,
                    )
                except TypeError:
                    retrieval_kwargs.pop("k", None)
                    memory_results = await retriever.retrieve_with_scope_fallback(
                        **retrieval_kwargs,
                    )
            elif hasattr(retriever, "retrieve_async"):
                retrieval_kwargs = {
                    "query": user_message,
                    "user_id": user_id,
                    "session_id": session_id,
                    "origin": "chat",
                    "k": chat_k,
                }
                try:
                    memory_results = await retriever.retrieve_async(**retrieval_kwargs)
                except TypeError:
                    retrieval_kwargs.pop("k", None)
                    memory_results = await retriever.retrieve_async(**retrieval_kwargs)
        elif skip_memory:
            logger.info("context_builder_memory_skipped reason=identity_or_capability_or_small_talk origin=chat")

        memory_results = self._limit_semantic_results(memory_results, chat_k)
        if not skip_memory:
            if memory_results:
                logger.info(
                    "context_builder_memory_injected count=%s origin=chat",
                    len(memory_results),
                )
            else:
                logger.info(
                    "context_builder_memory_skipped reason=retrieval_empty origin=chat"
                )

        return self._assemble_and_guard(
            system_prompt=system_prompt,
            memory_results=memory_results,
            history=conversation_history,
            user_message=user_message,
            origin="chat",
            history_limit=5,
        )
