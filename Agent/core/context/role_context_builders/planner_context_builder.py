from typing import List
from livekit.agents.llm import ChatContext, ChatMessage
from core.prompts import get_planner_prompt

class PlannerContextBuilder:
    """Builds context for the Planner, focusing on task creation."""
    
    @staticmethod
    def build(user_request: str, memory_summary: str = "", recent_history: List[ChatMessage] = None) -> ChatContext:
        messages = []
        
        # 1. System Prompt
        messages.append(ChatMessage(role="system", content=[get_planner_prompt()]))
        
        # 2. Context (Memory + History)
        context_str = f"User Request: {user_request}\n"
        if memory_summary:
            context_str += f"Relevant Memory: {memory_summary}\n"
            
        messages.append(ChatMessage(role="user", content=[context_str]))
        
        return ChatContext(messages)
