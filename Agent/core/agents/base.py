"""
Base Agent Interface for Specialization
Defines the contract for all specialized agents in the system.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass
import warnings
from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult
from core.response.agent_response import AgentResponse

logger = logging.getLogger(__name__)

@dataclass
class AgentContext:
    """Context passed to specialized agents"""
    user_id: str
    user_role: str
    conversation_history: list
    memory_context: str = ""
    custom_data: Dict[str, Any] = None

class SpecializedAgent(ABC):
    """Base class for all specialized agents"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"agents.{name}")
    
    async def can_accept(self, request: AgentHandoffRequest) -> AgentCapabilityMatch:
        """Phase 9A contract-aware capability scoring."""
        confidence = await self.can_handle(request.user_text, self._legacy_context_from_request(request))
        return AgentCapabilityMatch(
            agent_name=self.name,
            confidence=float(confidence),
            reason="legacy_can_handle_bridge",
            hard_constraints_passed=True,
        )

    async def handle(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        """Phase 9A contract-aware handler with legacy fallback bridge."""
        response = await self.execute(request.user_text, self._legacy_context_from_request(request))
        return AgentHandoffResult(
            handoff_id=request.handoff_id,
            trace_id=request.trace_id,
            source_agent=self.name,
            status="completed",
            user_visible_text=getattr(response, "display_text", None),
            voice_text=getattr(response, "voice_text", None),
            structured_payload={
                "display_text": getattr(response, "display_text", None),
                "voice_text": getattr(response, "voice_text", None),
                "mode": getattr(response, "mode", None),
                "structured_data": getattr(response, "structured_data", None),
            },
            next_action="respond",
            metadata={"bridge": "legacy_execute"},
        )

    def _legacy_context_from_request(self, request: AgentHandoffRequest) -> AgentContext:
        metadata = dict(request.metadata or {})
        return AgentContext(
            user_id=str(metadata.get("user_id") or "unknown"),
            user_role=str(metadata.get("user_role") or "USER"),
            conversation_history=list(metadata.get("conversation_history") or []),
            memory_context=str(metadata.get("memory_context") or request.context_slice or ""),
            custom_data=metadata,
        )

    async def can_handle(self, request: str, context: AgentContext) -> float:
        """
        Determine if this agent can handle the request.
        
        Returns:
            Confidence score (0.0 to 1.0)
        """
        warnings.warn(
            f"{self.__class__.__name__}.can_handle() is deprecated; implement can_accept()",
            DeprecationWarning,
            stacklevel=2,
        )
        raise NotImplementedError
    
    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        """
        Execute the request and return a response.
        """
        warnings.warn(
            f"{self.__class__.__name__}.execute() is deprecated; implement handle()",
            DeprecationWarning,
            stacklevel=2,
        )
        raise NotImplementedError
    
    def get_capabilities(self) -> list:
        """Return list of capabilities this agent provides"""
        return []
