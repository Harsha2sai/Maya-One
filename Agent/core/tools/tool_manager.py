import logging
import os
import asyncio
from typing import List, Any, Dict
import random
import time

print("🔍 DEBUG: ToolManager - Importing MCPToolsIntegration...")
from mcp_client.agent_tools import MCPToolsIntegration
print("🔍 DEBUG: ToolManager - Importing MCPServerSse...")
from mcp_client.server import MCPServerSse
print("🔍 DEBUG: ToolManager - Importing tool_registry...")
from core.registry.tool_registry import get_registry
print("🔍 DEBUG: ToolManager - Importing router...")
from core.routing.router import get_router
print("🔍 DEBUG: ToolManager - Importing WorkerToolRegistry...")
from core.tasks.workers.tool_registry import WorkerToolRegistry
print("🔍 DEBUG: ToolManager - Importing register_control_tools...")
from core.tools.control_tools import register_control_tools
print("🔍 DEBUG: ToolManager - Importing register_memory_tools...")
from core.tools.memory_tools import register_memory_tools
print("🔍 DEBUG: ToolManager - Importing register_planning_tool...")
from core.tools.planning_tools import register_planning_tool
print("🔍 DEBUG: ToolManager - Importing get_skill_registry...")
from core.skills.registry import get_skill_registry
print("🔍 DEBUG: ToolManager - Importing ExecutionGate...")
from core.governance.gate import ExecutionGate
from core.governance.audit import AuditLogger
from core.tools.execution_context import ExecutionContext, create_execution_context
print("🔍 DEBUG: ToolManager - Importing UserRole...")
from core.governance.types import UserRole, RiskLevel
print("🔍 DEBUG: ToolManager - Importing probe_tool_execution...")
from probes.runtime.probe_engine import probe_tool_execution
print("🔍 DEBUG: ToolManager - Importing get_chaos_config...")
from chaos.fault_injection import get_chaos_config
print("🔍 DEBUG: ToolManager - Importing publish_tool_execution...")
from core.communication import publish_tool_execution
from core.observability.trace_context import current_trace_id, get_trace_context, set_trace_context

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
        
        # ✅ FIX: Add MCP tools to agent._tools BEFORE local tools deduplication
        if hasattr(agent, '_tools') and isinstance(agent._tools, list):
            mcp_tool_count = len(agent._tools)
            if mcp_tool_count > 0:
                logger.info(f"✅ Agent initialized with {mcp_tool_count} MCP tools in agent._tools")
        
        # Combine tools for Router
        combined_tools = local_tools[:]
        if hasattr(agent, '_tools'):
             combined_tools.extend(agent._tools)

        # Register everything
        ToolManager._register_tools_shared(combined_tools)
        
        return agent

    @staticmethod
    async def load_all_tools(local_tools: List[Any]) -> List[Any]:
        """Load and combine MCP and Local tools without attaching to an agent instance."""
        mcp_server_url = os.environ.get("N8N_MCP_SERVER_URL")
        mcp_servers = []
        if mcp_server_url:
            mcp_servers.append(MCPServerSse(
                params={"url": mcp_server_url},
                cache_tools_list=True,
                name="SSE MCP Server"
            ))

        # Get MCP tools directly
        mcp_tools = []
        if mcp_servers:
             try:
                 # Hack: Create a dummy agent to extract tools via MCPToolsIntegration
                 # This avoids duplicating the MCP client logic
                 class DummyAgent:
                     def __init__(self, **kwargs): self._tools = []
                 
                 # Initialize dummy agent with MCP
                 dummy = await MCPToolsIntegration.create_agent_with_tools(
                     agent_class=DummyAgent,
                     agent_kwargs={},
                     mcp_servers=mcp_servers
                 )
                 mcp_tools = dummy._tools
             except Exception as e:
                 logger.error(f"Failed to load MCP tools: {e}")

        # Combine tools
        combined_tools = local_tools + mcp_tools
        
        # Register with registry and router
        ToolManager._register_tools_shared(combined_tools)
        
        return combined_tools

    @staticmethod
    def _register_tools_shared(all_tools: List[Any]):
        """Shared logic for registering tools with Registry and Router."""
        registry = get_registry()
        
        # Extract metadata and register
        metadata = ToolManager.extract_metadata(all_tools)
        if metadata:
            registry.register_from_mcp_tools(metadata)

        # Build canonical tool map once and fan out to adapters.
        tool_map: Dict[str, Any] = {}
        for t in all_tools:
            t_name = (getattr(t, 'name', None) or getattr(t, '__name__', '')).strip().lower()
            if t_name:
                tool_map[t_name] = t

        # Worker adapter now consumes canonical map from ToolManager.
        WorkerToolRegistry.set_canonical_tools(tool_map)
        invariant_ok = WorkerToolRegistry.assert_invariants()
        if not invariant_ok:
            logger.warning("⚠️ Tool registry invariant check failed; some worker-allowed tools are not loaded.")
        
        # Router Configuration
        ToolManager._configure_router(all_tools)

    @staticmethod
    def _configure_router(tools: List[Any]):
        # Build Optimized Tool Map for O(1) execution lookup
        tool_map = {}
        for t in tools:
            t_name = (getattr(t, 'name', None) or getattr(t, '__name__', '')).lower()
            if t_name: tool_map[t_name] = t

        # Configure Execution Router
        router = get_router()
        
        @probe_tool_execution
        async def tool_executor(name: str, params: dict, context: Any = None) -> str:
            start_ts = time.perf_counter()
            # CHAOS: Tool Failure Injection
            chaos_config = get_chaos_config()
            if chaos_config.enabled and chaos_config.tool_failure_rate > 0:
                if random.random() < chaos_config.tool_failure_rate:
                    logger.warning(f"🔥 CHAOS: Simulating failure for tool {name}")
                    return f"Error: Tool {name} failed (Simulated Chaos)"

            # 0. Context Resolution
            user_role = getattr(context, 'user_role', UserRole.GUEST)
            user_id = getattr(context, 'user_id', 'unknown')
            session_id = getattr(context, "session_id", None) or getattr(context, "turn_id", None)
            task_id = getattr(context, "task_id", None)
            incoming_trace_id = getattr(context, "trace_id", None)

            trace_snapshot = get_trace_context()
            trace_id = (
                str(incoming_trace_id or "").strip()
                or str(trace_snapshot.get("trace_id") or "").strip()
                or current_trace_id()
            )
            trace_ctx = set_trace_context(
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                task_id=task_id,
            )
            trace_id = trace_ctx["trace_id"]
            
            # 1. Audit Entry
            trace_id = AuditLogger.log_attempt(
                name,
                params,
                user_role,
                user_id,
                trace_id=trace_id,
                session_id=session_id,
                task_id=task_id,
            )
            
            # 2. Check Gate
            if not ExecutionGate.check_access(name, user_role):
                reason = ExecutionGate.get_denial_reason(name, user_role)
                AuditLogger.log_block(trace_id, name, reason)
                latency_ms = (time.perf_counter() - start_ts) * 1000.0
                logger.warning(
                    "tool_execution_blocked",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "user_id": user_id,
                        "task_id": task_id,
                        "tool_name": name,
                        "latency_ms": latency_ms,
                        "outcome": "blocked",
                    },
                )
                logger.warning(f"⛔ {reason}")
                return f"⛔ {reason}"

            # 2.5 PRE_TOOL hook
            try:
                from core.runtime.global_agent import GlobalAgentContainer
                _hook_reg = GlobalAgentContainer.get_hook_registry()
                if _hook_reg is not None:
                    from core.hooks.triggers import TOOL_PRE_EXECUTE
                    hook_ctx = {
                        "tool_name": name,
                        "params": params,
                        "user_id": user_id,
                        "session_id": session_id,
                        "trace_id": trace_id,
                    }
                    await _hook_reg.fire(TOOL_PRE_EXECUTE, hook_ctx)
            except Exception as _hook_err:
                logger.debug("pre_tool_hook_error tool=%s: %s", name, _hook_err)

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

                    # Create production ExecutionContext for tools
                    tool_ctx = create_execution_context(
                        context=context,
                        default_user_id=user_id,
                        default_session_id=session_id,
                    )

                    room = getattr(context, 'room', None)
                    turn_id = getattr(context, 'turn_id', None)
                    conversation_id = (
                        getattr(context, 'conversation_id', None)
                        or getattr(getattr(context, 'participant_metadata', None), 'get', lambda _k, _d=None: None)(
                            'conversation_id',
                            None,
                        )
                    )

                    # 3.1 Publish started event
                    if room and turn_id:
                        asyncio.create_task(
                            publish_tool_execution(
                                room,
                                turn_id,
                                name,
                                "started",
                                task_id=task_id,
                                conversation_id=conversation_id,
                            )
                        )

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
                    latency_ms = (time.perf_counter() - start_ts) * 1000.0
                    AuditLogger.log_result(
                        trace_id,
                        name,
                        result,
                        success=True,
                        latency_ms=latency_ms,
                        session_id=session_id,
                        user_id=user_id,
                        task_id=task_id,
                    )
                    logger.info(
                        "tool_execution",
                        extra={
                            "trace_id": trace_id,
                            "session_id": session_id,
                            "user_id": user_id,
                            "task_id": task_id,
                            "tool_name": name,
                            "latency_ms": latency_ms,
                            "outcome": "success",
                        },
                    )

                    # 4.05 POST_TOOL hook
                    try:
                        from core.runtime.global_agent import GlobalAgentContainer
                        _hook_reg = GlobalAgentContainer.get_hook_registry()
                        if _hook_reg is not None:
                            from core.hooks.triggers import TOOL_POST_EXECUTE
                            await _hook_reg.fire(TOOL_POST_EXECUTE, {
                                "tool_name": name,
                                "result": str(result)[:500],
                                "latency_ms": latency_ms,
                                "user_id": user_id,
                                "session_id": session_id,
                                "trace_id": trace_id,
                                "success": True,
                            })
                    except Exception as _hook_err:
                        logger.debug("post_tool_hook_error tool=%s: %s", name, _hook_err)

                    # 4.1 Publish finished event
                    if room and turn_id:
                        asyncio.create_task(
                            publish_tool_execution(
                                room,
                                turn_id,
                                name,
                                "finished",
                                message=str(result),
                                task_id=task_id,
                                conversation_id=conversation_id,
                            )
                        )
                        
                    return result
                    
                except Exception as e:
                    logger.error(f"Error executing {name}: {e}", exc_info=True)
                    latency_ms = (time.perf_counter() - start_ts) * 1000.0
                    AuditLogger.log_result(
                        trace_id,
                        name,
                        str(e),
                        success=False,
                        latency_ms=latency_ms,
                        session_id=session_id,
                        user_id=user_id,
                        task_id=task_id,
                    )
                    logger.error(
                        "tool_execution_failed",
                        extra={
                            "trace_id": trace_id,
                            "session_id": session_id,
                            "user_id": user_id,
                            "task_id": task_id,
                            "tool_name": name,
                            "latency_ms": latency_ms,
                            "outcome": "error",
                        },
                    )
                    return f"Error: {str(e)}"
            
            return f"Tool {name} not found."

        router.set_tool_executor(tool_executor)
        logger.info(f"✅ Router configured with {len(tool_map)} tools")
