"""
System Operator Agent - Specialized in system control and file operations.
"""
import logging
from core.agents.base import SpecializedAgent, AgentContext, AgentResponse
from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult
from core.response.response_formatter import ResponseFormatter
from core.registry.tool_registry import get_registry
from core.system.system_planner import SystemPlanner

logger = logging.getLogger(__name__)

class SystemOperatorAgent(SpecializedAgent):
    """
    Specialized agent for system operations.
    Handles file operations, app control, and system commands.
    """
    
    def __init__(self):
        super().__init__("system_operator")
        self.registry = get_registry()
        self._planner = SystemPlanner()
        self.system_keywords = [
            'open', 'close', 'launch', 'start', 'stop', 'kill',
            'file', 'folder', 'directory', 'application', 'app',
            'run', 'execute', 'terminal', 'command'
        ]
    
    async def can_handle(self, request: str, context: AgentContext) -> float:
        """Determine if this is a system operation request"""
        request_lower = request.lower()
        
        # Check for system keywords
        keyword_matches = sum(1 for kw in self.system_keywords if kw in request_lower)
        
        # Check for system-related tools in registry
        system_tools = self.registry.get_tools_by_category("system_control")
        tool_match = any(tool.name in request_lower for tool in system_tools)
        
        # Calculate confidence
        confidence = 0.0
        if keyword_matches > 0:
            confidence += 0.5 * min(keyword_matches, 2)
        if tool_match:
            confidence += 0.4
        
        return min(confidence, 1.0)

    async def can_accept(self, request: AgentHandoffRequest) -> AgentCapabilityMatch:
        confidence = await self.can_handle(request.user_text, self._legacy_context_from_request(request))
        return AgentCapabilityMatch(
            agent_name=self.name,
            confidence=confidence,
            reason="system_keyword_match",
            hard_constraints_passed=bool(str(request.user_text or "").strip()),
        )
    
    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        """Execute system operation"""
        try:
            self.logger.info(f"⚙️ System Operator processing: {request}")
            
            # Match to appropriate system tool
            best_match = self.registry.get_best_match(request)
            
            if best_match and best_match in [t.name for t in self.registry.get_tools_by_category("system_control")]:
                return ResponseFormatter.build_response(
                    f"I'll use the {best_match} tool to handle this.",
                    structured_data={"tool": best_match, "category": "system_control"},
                    mode="direct",
                )
            else:
                return ResponseFormatter.build_response(
                    "I'm not sure which system operation you want me to perform.",
                    structured_data={"error": "No matching system tool found"},
                )
            
        except Exception as e:
            self.logger.error(f"❌ System Operator error: {e}")
            return ResponseFormatter.build_response(
                "I encountered an error with this system operation.",
                structured_data={"error": str(e)},
            )

    async def handle(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        actions = await self._planner._parse_intent(request.user_text, trace_id=request.trace_id)
        if not actions:
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=self.name,
                status="rejected",
                user_visible_text="I couldn't determine a safe system intent for that request.",
                voice_text=None,
                structured_payload={"actions": []},
                next_action="fallback_to_maya",
                error_code="system_intent_unresolved",
                error_detail="No safe actions parsed from intent",
            )

        first_action = actions[0]
        structured_payload = {
            "action_type": first_action.action_type.value,
            "tool_name": first_action.action_type.value.lower(),
            "parameters": dict(first_action.params or {}),
            "requires_confirmation": bool(first_action.requires_confirmation or first_action.destructive),
            "rollback_available": bool(first_action.rollback_recipe),
            "trace_id": request.trace_id,
            "action_count": len(actions),
        }
        return AgentHandoffResult(
            handoff_id=request.handoff_id,
            trace_id=request.trace_id,
            source_agent=self.name,
            status="completed",
            user_visible_text="System intent validated.",
            voice_text=None,
            structured_payload=structured_payload,
            next_action="continue",
        )
    
    def get_capabilities(self) -> list:
        return [
            "Application control (open/close)",
            "File operations",
            "System commands",
            "Process management"
        ]
