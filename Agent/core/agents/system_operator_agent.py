"""
System Operator Agent - Specialized in system control and file operations.
"""
import logging
from core.agents.base import SpecializedAgent, AgentContext, AgentResponse
from core.registry.tool_registry import get_registry

logger = logging.getLogger(__name__)

class SystemOperatorAgent(SpecializedAgent):
    """
    Specialized agent for system operations.
    Handles file operations, app control, and system commands.
    """
    
    def __init__(self):
        super().__init__("system_operator")
        self.registry = get_registry()
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
    
    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        """Execute system operation"""
        try:
            self.logger.info(f"⚙️ System Operator processing: {request}")
            
            # Match to appropriate system tool
            best_match = self.registry.get_best_match(request)
            
            if best_match and best_match in [t.name for t in self.registry.get_tools_by_category("system_control")]:
                return AgentResponse(
                    success=True,
                    content=f"I'll use the {best_match} tool to handle this.",
                    data={"tool": best_match, "category": "system_control"},
                    requires_handoff=True,
                    handoff_to="tool_executor"
                )
            else:
                return AgentResponse(
                    success=False,
                    content="I'm not sure which system operation you want me to perform.",
                    error="No matching system tool found"
                )
            
        except Exception as e:
            self.logger.error(f"❌ System Operator error: {e}")
            return AgentResponse(
                success=False,
                content="I encountered an error with this system operation.",
                error=str(e)
            )
    
    def get_capabilities(self) -> list:
        return [
            "Application control (open/close)",
            "File operations",
            "System commands",
            "Process management"
        ]
