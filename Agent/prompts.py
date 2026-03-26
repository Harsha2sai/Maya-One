"""
Maya Voice Assistant Prompts
Optimized for natural conversation with selective tool calling.
"""

from core.prompts import get_maya_primary_prompt

AGENT_INSTRUCTION = get_maya_primary_prompt()

SESSION_INSTRUCTION = """
Say hi briefly. Don't call any tools for the greeting.
"""
