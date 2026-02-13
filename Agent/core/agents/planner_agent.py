"""
Planner Agent - Coordinates complex multi-step tasks.
"""
import logging
from core.agents.base import SpecializedAgent, AgentContext, AgentResponse
from core.intelligence.planner import task_planner

logger = logging.getLogger(__name__)

class PlannerAgent(SpecializedAgent):
    """
    Specialized agent for planning and coordination.
    Decomposes complex goals into actionable steps.
    """
    
    def __init__(self):
        super().__init__("planner")
        self.planner = task_planner
        self.planning_keywords = [
            'plan', 'organize', 'prepare', 'schedule', 'coordinate',
            'multiple', 'series', 'sequence', 'steps', 'first', 'then'
        ]
    
    async def can_handle(self, request: str, context: AgentContext) -> float:
        """Determine if this requires planning"""
        request_lower = request.lower()
        
        # Check for planning keywords
        keyword_matches = sum(1 for kw in self.planning_keywords if kw in request_lower)
        
        # Check for multi-step indicators
        has_conjunctions = any(word in request_lower for word in ['and then', 'after that', 'next', 'finally'])
        has_multiple_verbs = request_lower.count('and') > 1
        
        # Calculate confidence
        confidence = 0.0
        if keyword_matches > 0:
            confidence += 0.4 * min(keyword_matches, 2)
        if has_conjunctions:
            confidence += 0.3
        if has_multiple_verbs:
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        """Create and manage execution plan"""
        try:
            self.logger.info(f"📋 Planner Agent processing: {request}")
            
            # Check if a plan is already active
            if self.planner.is_active:
                progress = self.planner.get_progress_report()
                return AgentResponse(
                    success=True,
                    content=f"Continuing with the current plan:\n\n{progress}",
                    data={"active_plan": True}
                )
            
            # For now, indicate that planning capability is available
            return AgentResponse(
                success=True,
                content="I can help break this down into steps. Let me think about the best approach.",
                data={"requires_planning": True},
                requires_handoff=True,
                handoff_to="llm_planner"  # LLM will generate the actual plan
            )
            
        except Exception as e:
            self.logger.error(f"❌ Planner Agent error: {e}")
            return AgentResponse(
                success=False,
                content="I had trouble creating a plan.",
                error=str(e)
            )
    
    def get_capabilities(self) -> list:
        return [
            "Multi-step task decomposition",
            "Workflow coordination",
            "Plan tracking and execution",
            "Progress reporting"
        ]
