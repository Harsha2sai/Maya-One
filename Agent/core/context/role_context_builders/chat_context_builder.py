from typing import List
from livekit.agents.llm import ChatContext, ChatMessage
from core.prompts import get_maya_primary_prompt

class ChatContextBuilder:
    """Builds context for casual conversation, excluding heavy task details."""
    
    @staticmethod
    def build(history: List[ChatMessage], system_prompt: str = None) -> ChatContext:
        messages = []
        
        # 1. System Prompt
        sys_prompt = system_prompt or get_maya_primary_prompt()
        messages.append(ChatMessage(role="system", content=[sys_prompt]))
        
        # 2. Recent History (Memory Light)
        # Filter out complex tool outputs from history to keep it clean?
        # For now, just pass recent history.
        messages.extend(history[-10:]) 
        
        return ChatContext(messages)
