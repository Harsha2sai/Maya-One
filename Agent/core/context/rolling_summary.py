
import logging
import asyncio
import re
from typing import List, Optional, Any
from livekit.agents.llm import ChatContext, ChatMessage
from core.context.context_config import MAX_RECENT_TURNS, SUMMARY_THRESHOLD
from providers import ProviderFactory
from config.settings import settings

logger = logging.getLogger(__name__)

class RollingContextManager:
    """
    Manages the rolling window of conversation history and session summarization.
    """
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.session_summary: str = ""
        self.turns_since_summary: int = 0
        self.lock = asyncio.Lock()
        
        # We need an LLM for summarization. 
        # Ideally this is passed in or obtained from factory.
        # For now, we'll lazy load or get from factory to avoid init issues.
        self._llm = None

    async def _get_llm(self):
        if not self._llm:
            try:
                self._llm = ProviderFactory.get_llm(settings.llm_provider, settings.llm_model)
            except Exception as e:
                logger.error(f"Failed to get LLM for summarization: {e}")
        return self._llm

    def get_recent_turns(self, chat_ctx: ChatContext) -> List[ChatMessage]:
        """
        Returns the last MAX_RECENT_TURNS messages from the chat context.
        Excludes system messages as those are rebuilt by ContextBuilder.
        """
        messages = chat_ctx.messages
        if callable(messages):
            messages = messages()
        
        # Filter out system messages and get the last N
        relevant_msgs = [m for m in messages if m.role != "system"]
        return relevant_msgs[-MAX_RECENT_TURNS:]

    async def update_session(self, chat_ctx: ChatContext):
        """
        Called after each turn to update counters and potentially trigger summarization.
        """
        async with self.lock:
            self.turns_since_summary += 1
            
            if self.turns_since_summary >= SUMMARY_THRESHOLD:
                # Trigger background summarization
                # We copy the context/messages to avoid race conditions during async execution
                messages_snapshot = self.get_recent_turns(chat_ctx)
                if messages_snapshot:
                    asyncio.create_task(self._generate_summary(messages_snapshot))
                    self.turns_since_summary = 0

    async def _generate_summary(self, recent_messages: List[ChatMessage]):
        """
        Generates a summary of the recent conversation chunk and appends to session summary.
        """
        llm = await self._get_llm()
        if not llm:
            logger.warning("Skipping summarization: LLM not available")
            return

        try:
            # Convert messages to text format
            transcript = "\n".join([f"{m.role}: {m.content}" for m in recent_messages])
            
            prompt = f"""
            Summarize the following conversation chunk into 1-2 factual bullet points.
            Focus on user intent, key info provided, and actions taken.
            No fluff.
            
            Conversation:
            {transcript}
            
            Current Session Summary:
            {self.session_summary}
            
            New Summary (append to current):
            """
            
            # Create a localized context for the summarizer
            # We use a simple chat call. 
            # Note: We need to be careful not to create infinite loops if this LLM call 
            # somehow triggers the main agent pipeline, but ProviderFactory.get_llm returns 
            # a base LLM instance, not the SmartLLM, so we should be safe.
            
            # Simple one-shot chat
            # We construct a temporary ChatContext
            summary_ctx = ChatContext(
                [
                    ChatMessage(role="system", content=["You are a concise summarizer."]),
                    ChatMessage(role="user", content=[prompt])
                ]
            )
            
            stream = llm.chat(chat_ctx=summary_ctx)
            result = ""
            async for chunk in stream:
                 if chunk.choices:
                     delta = chunk.choices[0].delta.content
                     if delta:
                         result += delta
            
            # Update summary
            if result.strip():
                async with self.lock:
                    if self.session_summary:
                        self.session_summary += "\n" + result.strip()
                    else:
                        self.session_summary = result.strip()
                
                logger.info(f"📝 Updated Session Summary for {self.user_id}: {self.session_summary[:50]}...")
                
        except Exception as e:
            logger.error(f"❌ Summarization failed: {e}")


class RollingSummarizer:
    """
    Lightweight tier-3 summarizer used by ContextGuard.
    Deterministic by default to avoid adding LLM latency in hot path.
    """

    def summarize_sync(
        self,
        messages: List[dict[str, Any]],
        token_budget: int = 3000,
    ) -> str:
        if not messages:
            return ""

        snippets: list[str] = []
        for msg in messages:
            role = "User" if str(msg.get("role", "user")) == "user" else "Assistant"
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            compact = re.sub(r"\s+", " ", content)
            if len(compact) > 220:
                compact = f"{compact[:217].rstrip()}..."
            snippets.append(f"- {role}: {compact}")

        if not snippets:
            return ""

        summary = "[Earlier conversation summary]\n" + "\n".join(snippets[-8:])

        if token_budget <= 0:
            return ""
        approx_token_budget = token_budget * 4
        if len(summary) > approx_token_budget:
            summary = summary[:approx_token_budget].rstrip() + "..."
        return summary
