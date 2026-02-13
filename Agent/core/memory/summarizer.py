
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from llama_index.llms.groq import Groq
from llama_index.core.llms import ChatMessage, MessageRole

logger = logging.getLogger(__name__)

class Summarizer:
    """
    Summarizes conversation history to maintain manageable context windows.
    Uses Groq (Llama 3) for fast, cost-effective summarization.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ GROQ_API_KEY not found. Summarization will be disabled.")
            self.llm = None
        else:
            try:
                self.llm = Groq(model="llama-3.1-8b-instant", api_key=self.api_key)
                logger.info("✅ Summarizer initialized with Groq (Llama 3.1)")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Summarizer LLM: {e}")
                self.llm = None

    async def summarize_messages(self, messages: List[Dict[str, str]]) -> str:
        """
        Summarize a list of message dictionaries into a concise narrative.
        """
        if not self.llm:
            return ""

        if not messages:
            return ""

        try:
            # Convert dict messages to text for the prompt
            transcript = ""
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                transcript += f"{role.upper()}: {content}\n"

            prompt = (
                f"Summarize the following conversation transcript into a concise paragraph. "
                f"Focus on key facts, user preferences, and implementation details. "
                f"Do not lose important context.\n\n"
                f"TRANSCRIPT:\n{transcript}\n\nSUMMARY:"
            )

            response = await self.llm.acomplete(prompt)
            return response.text.strip()

        except Exception as e:
            logger.error(f"❌ Summarization failed: {e}")
            return ""
