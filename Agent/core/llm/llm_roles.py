"""
Defines distinct LLM roles and their configurations for the agent.

Each role has specialized prompts, tool access, and temperature settings essentially 
creating different 'personas' for different parts of the execution pipeline.
"""
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional
from core.prompts import (
    get_maya_primary_prompt,
    get_planner_prompt,
    get_tool_router_prompt,
    get_worker_prompt,
)

class LLMRole(Enum):
    CHAT = "chat"       # Casual conversation, light memory
    PLANNER = "planner" # High-level task breakdown, full context
    TOOL = "tool"       # Routing and parameter extraction
    WORKER = "worker"   # Precise execution with tool schemas

@dataclass
class RoleConfig:
    """Configuration for a specific LLM role."""
    role: LLMRole
    description: str
    temperature: float
    token_limit: int = 4000
    system_prompt_template: str = ""
    allowed_tools: List[str] = field(default_factory=list) # Empty means verify dynamic/none
    include_memory: bool = False
    include_tools: bool = False
    provider: Optional[str] = None # Start of Model Routing
    model: Optional[str] = None

def _default_provider() -> str:
    return os.getenv("LLM_PROVIDER", "groq")

def _default_model() -> str:
    return os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

def _role_provider(role_key: str) -> str:
    return os.getenv(f"MAYA_{role_key}_LLM_PROVIDER", _default_provider())

def _role_model(role_key: str) -> str:
    return os.getenv(f"MAYA_{role_key}_LLM_MODEL", _default_model())

# Role Definitions

CHAT_CONFIG = RoleConfig(
    role=LLMRole.CHAT,
    description="Friendly conversational assistant",
    temperature=0.7,
    include_memory=True,
    include_tools=True, # Allow tools for memory/retrieval
    system_prompt_template=get_maya_primary_prompt(),
    provider=_role_provider("CHAT"),
    model=_role_model("CHAT")
)

PLANNER_CONFIG = RoleConfig(
    role=LLMRole.PLANNER,
    description="Strategic task planner",
    temperature=0.2, # Low temp for structured output
    include_memory=True, # Needs context to plan
    include_tools=False, # Planner NEVER calls tools
    system_prompt_template=get_planner_prompt(),
    provider=_role_provider("PLANNER"),
    model=_role_model("PLANNER")
)

TOOL_ROUTER_CONFIG = RoleConfig(
    role=LLMRole.TOOL,
    description="Tool selector and parameter extractor",
    temperature=0.1, # Very low for precision
    include_memory=False, # Minimal history needed
    include_tools=True, # Needs tool schemas
    system_prompt_template=get_tool_router_prompt(),
    provider=_role_provider("TOOL"),
    model=_role_model("TOOL")
)

WORKER_CONFIG = RoleConfig(
    role=LLMRole.WORKER,
    description="Step execution specialist",
    temperature=0.3, # Balanced for reasoning + precision
    include_memory=True, # Needs step context
    include_tools=True, # Needs tool schemas to execute
    system_prompt_template=get_worker_prompt(),
    provider=_role_provider("WORKER"),
    model=_role_model("WORKER")
)

def get_role_config(role: LLMRole) -> RoleConfig:
    if role == LLMRole.CHAT:
        return CHAT_CONFIG
    elif role == LLMRole.PLANNER:
        return PLANNER_CONFIG
    elif role == LLMRole.TOOL:
        return TOOL_ROUTER_CONFIG
    elif role == LLMRole.WORKER:
        return WORKER_CONFIG
    raise ValueError(f"Unknown role: {role}")
