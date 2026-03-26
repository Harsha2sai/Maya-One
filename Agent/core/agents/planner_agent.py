"""
Planner Agent - Coordinates complex multi-step tasks.
"""
import logging
import json
from core.agents.base import SpecializedAgent, AgentContext, AgentResponse
from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult
from core.response.response_formatter import ResponseFormatter
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

    async def can_accept(self, request: AgentHandoffRequest) -> AgentCapabilityMatch:
        confidence = await self.can_handle(request.user_text, self._legacy_context_from_request(request))
        return AgentCapabilityMatch(
            agent_name=self.name,
            confidence=confidence,
            reason="planning_keyword_match",
            hard_constraints_passed=request.execution_mode == "planning",
        )
    
    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        """Create and manage execution plan"""
        try:
            self.logger.info(f"📋 Planner Agent processing: {request}")
            
            # Check if a plan is already active
            if self.planner.is_active:
                progress = self.planner.get_progress_report()
                return ResponseFormatter.build_response(
                    f"Continuing with the current plan:\n\n{progress}",
                    structured_data={"active_plan": True},
                    mode="planning",
                )
            
            # For now, indicate that planning capability is available
            return ResponseFormatter.build_response(
                "I can help break this down into steps. Let me think about the best approach.",
                structured_data={"requires_planning": True},
                mode="planning",
            )
            
        except Exception as e:
            self.logger.error(f"❌ Planner Agent error: {e}")
            return ResponseFormatter.build_response(
                "I had trouble creating a plan.",
                structured_data={"error": str(e)},
                mode="planning",
            )

    async def handle(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        response = await self.execute(request.user_text, self._legacy_context_from_request(request))
        structured_payload = {
            "requires_planning": True,
            "task_plan_schema": {
                "title": "string",
                "steps": [
                    {
                        "seq": 1,
                        "title": "string",
                        "tool": "string|null",
                        "worker": "string",
                        "parameters": {},
                    }
                ],
            },
            "task_plan_schema_json": json.dumps(
                {
                    "title": "string",
                    "steps": [
                        {
                            "seq": 1,
                            "title": "string",
                            "tool": None,
                            "worker": "general",
                            "parameters": {},
                        }
                    ],
                }
            ),
        }
        return AgentHandoffResult(
            handoff_id=request.handoff_id,
            trace_id=request.trace_id,
            source_agent=self.name,
            status="completed",
            user_visible_text=response.display_text,
            voice_text=response.voice_text,
            structured_payload=structured_payload,
            next_action="continue",
        )
    
    def get_capabilities(self) -> list:
        return [
            "Multi-step task decomposition",
            "Workflow coordination",
            "Plan tracking and execution",
            "Progress reporting"
        ]
