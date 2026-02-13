import logging
import os
import asyncio
from typing import List, Any, Dict

from mcp_client.agent_tools import MCPToolsIntegration
from mcp_client.server import MCPServerSse
from core.registry.tool_registry import get_registry
from core.routing.router import get_router
from core.tools.control_tools import register_control_tools
from core.tools.memory_tools import register_memory_tools
from core.tools.planning_tools import register_planning_tool
from core.skills.registry import get_skill_registry
from core.governance.gate import ExecutionGate
from core.governance.audit import AuditLogger
from core.governance.types import UserRole, RiskLevel
from probes.runtime.probe_engine import probe_tool_execution
from chaos.fault_injection import get_chaos_config
from core.communication import publish_tool_execution
import random

logger = logging.getLogger(__name__)

class ToolManager:
    @staticmethod
    def extract_metadata(tools: List[Any]) -> List[Dict[str, Any]]:
        """Extract metadata from local tools for registry registration."""
        tool_data = []
        for tool in tools:
            try:
                # Handle LiveKit FunctionTool or raw functions
                t_name = getattr(tool, 'name', None) or getattr(tool, '__name__', 'unknown')
                t_desc = getattr(tool, 'description', None) or getattr(tool, '__doc__', '')
                t_params = getattr(tool, 'parameters', {})
                
                tool_data.append({
                    'name': t_name,
                    'description': t_desc,
                    'inputSchema': {'properties': t_params} if t_params else {}
                })
            except Exception as e:
                logger.warning(f"⚠️ Failed to extract metadata from tool {tool}: {e}")
        return tool_data

    @staticmethod
    async def initialize_agent_with_mcp(
        agent_class, 
        agent_kwargs, 
        local_tools: List[Any]
    ):
        """Setup MCP servers, create agent with combined tools, and configure router."""
        mcp_server_url = os.environ.get("N8N_MCP_SERVER_URL")
        mcp_servers = []
        
        if mcp_server_url:
            mcp_servers.append(MCPServerSse(
                params={"url": mcp_server_url},
                cache_tools_list=True,
                name="SSE MCP Server"
            ))
            logger.info(f"🌐 Configured MCP Server: {mcp_server_url}")

        agent = await MCPToolsIntegration.create_agent_with_tools(
            agent_class=agent_class,
            agent_kwargs=agent_kwargs,
            mcp_servers=mcp_servers
        )
        
        # Build Tool Registry for Intent Matching
        registry = get_registry()
        local_metadata = ToolManager.extract_metadata(local_tools)
        if local_metadata:
            registry.register_from_mcp_tools(local_metadata)
            
        if hasattr(agent, '_tools'):
            mcp_metadata = []
            local_names = [t['name'] for t in local_metadata]
            for tool in agent._tools:
                t_name = getattr(tool, 'name', None) or getattr(tool, '__name__', 'unknown')
                if t_name not in local_names:
                    mcp_metadata.append({
                        'name': t_name,
                        'description': getattr(tool, 'description', ''),
                        'inputSchema': {'properties': getattr(tool, 'parameters', {})}
                    })
            if mcp_metadata:
                registry.register_from_mcp_tools(mcp_metadata)

        # Build Optimized Tool Map for O(1) execution lookup
        tool_map = {}
        for t in local_tools:
            t_name = (getattr(t, 'name', None) or getattr(t, '__name__', '')).lower()
            if t_name: tool_map[t_name] = t
                
        if hasattr(agent, '_tools'):
            for t in agent._tools:
                t_name = (getattr(t, 'name', None) or getattr(t, '__name__', '')).lower()
                if t_name: tool_map[t_name] = t

        # Configure Execution Router
        router = get_router()
        
        @probe_tool_execution
        async def tool_executor(name: str, params: dict, context: Any = None) -> str:
            # CHAOS: Tool Failure Injection
            chaos_config = get_chaos_config()
            if chaos_config.enabled and chaos_config.tool_failure_rate > 0:
                if random.random() < chaos_config.tool_failure_rate:
                    logger.warning(f"🔥 CHAOS: Simulating failure for tool {name}")
                    return f"Error: Tool {name} failed (Simulated Chaos)"

            # 0. Context Resolution

            # 0. Context Resolution
            user_role = getattr(context, 'user_role', UserRole.GUEST)
            user_id = getattr(context, 'user_id', 'unknown')
            
            # 1. Audit Entry
            trace_id = AuditLogger.log_attempt(name, params, user_role, user_id)
            
            # 2. Check Gate
            if not ExecutionGate.check_access(name, user_role):
                reason = ExecutionGate.get_denial_reason(name, user_role)
                AuditLogger.log_block(trace_id, name, reason)
                logger.warning(f"⛔ {reason}")
                return f"⛔ {reason}"

            # 3. Execute
            logger.info(f"🔧 Executing tool: {name} | Role: {user_role.name}")
            found_tool = tool_map.get(name.lower())
            
            # Fallback to SkillRegistry for dynamic skills
            if not found_tool:
                skill_registry = get_skill_registry()
                found_tool = skill_registry.get_skill_function(name)
            
            if found_tool:
                try:
                    result = None
                    
                    # Mock Context with user_id for persistence tools
                    class MockJobContext:
                        def __init__(self, uid): self.user_id = uid
                    
                    class SimpleContext: 
                        def __init__(self, uid): self.job_context = MockJobContext(uid)
                    
                    tool_ctx = SimpleContext(user_id)
                    
                    room = getattr(context, 'room', None)
                    turn_id = getattr(context, 'turn_id', None)

                    # 3.1 Publish started event
                    if room and turn_id:
                        asyncio.create_task(publish_tool_execution(room, turn_id, name, "started"))

                    # Strategy 1: LiveKit FunctionTool (wrapped)
                    if hasattr(found_tool, '__wrapped__'):
                        result = await found_tool.__wrapped__(tool_ctx, **params)
                    # Strategy 2: LiveKit FunctionTool.call
                    elif hasattr(found_tool, 'call'):
                        result = await found_tool.call(params, tool_ctx)
                    # Strategy 3: Raw Callable
                    elif callable(found_tool):
                        # Inspect to see if it accepts context
                        import inspect
                        try:
                            sig = inspect.signature(found_tool)
                            if 'context' in sig.parameters:
                                result = await found_tool(tool_ctx, **params)
                            else:
                                result = await found_tool(**params)
                        except ValueError:
                             # Some built-ins or wrapped funcs might not have signature
                             result = await found_tool(**params)

                    else:
                        return f"Tool {name} is not callable"
                    
                    # 4. Audit Result
                    AuditLogger.log_result(trace_id, name, result, success=True)
                    
                    # 4.1 Publish finished event
                    if room and turn_id:
                        asyncio.create_task(publish_tool_execution(room, turn_id, name, "finished"))
                        
                    return result
                    
                except Exception as e:
                    logger.error(f"Error executing {name}: {e}", exc_info=True)
                    AuditLogger.log_result(trace_id, name, str(e), success=False)
                    return f"Error: {str(e)}"
            
            return f"Tool {name} not found."

        router.set_tool_executor(tool_executor)
        logger.info(f"✅ Router configured with {len(tool_map)} tools")
        
        return agent
