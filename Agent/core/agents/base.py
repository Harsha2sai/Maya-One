"""
Base Agent Interface for Specialization
Defines the contract for all specialized agents in the system.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AgentContext:
    """Context passed to specialized agents"""
    user_id: str
    user_role: str
    conversation_history: list
    memory_context: str = ""
    custom_data: Dict[str, Any] = None

@dataclass
class AgentResponse:
    """Response from a specialized agent"""
    success: bool
    content: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    requires_handoff: bool = False
    handoff_to: Optional[str] = None

class SpecializedAgent(ABC):
    """Base class for all specialized agents"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"agents.{name}")
    
    @abstractmethod
    async def can_handle(self, request: str, context: AgentContext) -> float:
        """
        Determine if this agent can handle the request.
        
        Returns:
            Confidence score (0.0 to 1.0)
        """
        pass
    
    @abstractmethod
    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        """
        Execute the request and return a response.
        """
        pass
    
    def get_capabilities(self) -> list:
        """Return list of capabilities this agent provides"""
        return []
