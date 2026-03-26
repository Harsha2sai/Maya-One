from typing import List
from livekit.agents.llm import ChatContext, ChatMessage
from core.prompts import get_tool_router_prompt

class ToolContextBuilder:
    """Builds context for Tool Router (if used separately) or dynamic tool validation."""
    
    @staticmethod
    def build(tool_name: str, args_str: str) -> ChatContext:
        messages = []
        
        # 1. System Prompt
        messages.append(ChatMessage(role="system", content=[get_tool_router_prompt()]))
        
        # 2. Validation Request
        content = f"Tool: {tool_name}\nArguments: {args_str}\nValidate and extract."
        messages.append(ChatMessage(role="user", content=[content]))
        
        return ChatContext(messages)
