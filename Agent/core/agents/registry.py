"""
Agent Registry - Manages and routes to specialized agents.
"""
import logging
from typing import List, Optional, Tuple
from core.agents.base import SpecializedAgent, AgentContext, AgentResponse
from core.agents.research_agent import ResearchAgent
from core.agents.system_operator_agent import SystemOperatorAgent
from core.agents.planner_agent import PlannerAgent

logger = logging.getLogger(__name__)

class AgentRegistry:
    """
    Central registry for specialized agents.
    Routes requests to the most appropriate agent.
    """
    
    def __init__(self):
        self.agents: List[SpecializedAgent] = []
        self._register_default_agents()
    
    def _register_default_agents(self):
        """Register the built-in specialized agents"""
        self.register_agent(ResearchAgent())
        self.register_agent(SystemOperatorAgent())
        self.register_agent(PlannerAgent())
        logger.info(f"✅ Registered {len(self.agents)} specialized agents")
    
    def register_agent(self, agent: SpecializedAgent):
        """Add a new specialized agent to the registry"""
        self.agents.append(agent)
        logger.info(f"📝 Registered agent: {agent.name}")
    
    async def route(self, request: str, context: AgentContext) -> Tuple[Optional[SpecializedAgent], float]:
        """
        Find the best agent to handle the request.
        
        Returns:
            Tuple of (agent, confidence_score)
        """
        best_agent = None
        best_score = 0.0
        
        for agent in self.agents:
            score = await agent.can_handle(request, context)
            logger.debug(f"Agent {agent.name} confidence: {score:.2f}")
            
            if score > best_score:
                best_score = score
                best_agent = agent
        
        if best_agent:
            logger.info(f"🎯 Routing to {best_agent.name} (confidence: {best_score:.2f})")
        
        return best_agent, best_score
    
    async def execute(self, request: str, context: AgentContext, min_confidence: float = 0.5) -> AgentResponse:
        """
        Route and execute request with the best agent.
        
        Args:
            request: User request
            context: Agent context
            min_confidence: Minimum confidence threshold for routing
        
        Returns:
            AgentResponse from the selected agent or default response
        """
        agent, confidence = await self.route(request, context)
        
        if agent and confidence >= min_confidence:
            return await agent.execute(request, context)
        else:
            # No agent confident enough, return default
            logger.info("⚠️ No specialized agent available, using default handling")
            return AgentResponse(
                success=False,
                content="I'll handle this with my default capabilities.",
                requires_handoff=True,
                handoff_to="default_llm"
            )
    
    def list_agents(self) -> List[dict]:
        """Get information about all registered agents"""
        return [
            {
                "name": agent.name,
                "capabilities": agent.get_capabilities()
            }
            for agent in self.agents
        ]

# Global registry instance
_registry: Optional[AgentRegistry] = None

def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
