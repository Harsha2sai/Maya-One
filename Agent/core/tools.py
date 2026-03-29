import logging
import os
import asyncio
from typing import List, Any, Dict

from mcp_client.agent_tools import MCPToolsIntegration
from mcp_client.server import MCPServerSse
from plugins.manager import PluginManager
from tool_registry import get_registry
from execution_router import get_router

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

        # Load dynamic plugins from the plugins directory
        plugin_manager = PluginManager()
        plugin_servers = []
        try:
            plugin_servers = plugin_manager.load_all_plugins()
            logger.info(f"🧩 Discovered {len(plugin_manager.plugins)} plugins")
        except Exception as e:
            logger.error(f"⚠️ Error loading plugins: {e}")

        # Note: We do NOT pass plugin_servers to create_agent_with_tools
        # as we want to handle routing through PluginManager/Adapters ourselves.
        # However, we DO need to manually connect to their MCP processes.
        for server in plugin_servers:
            if not getattr(server, 'connected', False):
                try:
                    logger.info(f"Connecting to plugin server: {server.name}...")
                    await asyncio.wait_for(server.connect(), timeout=5.0)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to connect to plugin server {server.name}: {e}")

        agent = await MCPToolsIntegration.create_agent_with_tools(
            agent_class=agent_class,
            agent_kwargs=agent_kwargs,
            mcp_servers=mcp_servers # Only original servers (like n8n)
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
        
        async def tool_executor(name: str, params: dict) -> str:
            logger.info(f"🛠️ Executing tool: {name}")

            # 1. Safety Check: Rate Limits & Confirmation
            safe, reason = plugin_manager.check_safety(name)
            if not safe:
                logger.error(f"🚨 Tool execution blocked: {reason}")
                return f"Error: {reason}"
            if reason == "Confirmation Required":
                logger.warning(f"⚠️ Tool {name} requires confirmation. Simulation: User approved.")
                # In a real app, this would pause and wait for user voice/UI input

            # 2. Routing Logic: Plugin vs Local Tool
            target_plugin = None
            for plugin in plugin_manager.plugins.values():
                if any(t.get("name") == name for t in plugin.tools):
                    target_plugin = plugin
                    break

            if target_plugin:
                try:
                    return await target_plugin.invoke(name, params)
                except Exception as e:
                    logger.error(f"Error invoking plugin tool {name}: {e}")
                    return f"Error: {str(e)}"

            # Fallback to Local Tool Map
            found_tool = tool_map.get(name.lower())
            
            if found_tool:
                try:
                    # Strategy 1: LiveKit FunctionTool (wrapped)
                    if hasattr(found_tool, '__wrapped__'):
                        class SimpleContext: pass
                        return await found_tool.__wrapped__(SimpleContext(), **params)
                    # Strategy 2: LiveKit FunctionTool.call
                    elif hasattr(found_tool, 'call'):
                        class SimpleContext: pass
                        return await found_tool.call(params, SimpleContext())
                    # Strategy 3: Raw Callable
                    elif callable(found_tool):
                        class SimpleContext: pass
                        return await found_tool(SimpleContext(), **params)
                    else:
                        return f"Tool {name} is not callable"
                except Exception as e:
                    logger.error(f"Error executing {name}: {e}", exc_info=True)
                    return f"Error: {str(e)}"
            
            return f"Tool {name} not found."

        # Register Proxy Tools for all discovered plugins
        # (Must be after tool_executor is defined for the closure to work correctly)
        from livekit.agents.llm import function_tool
        import inspect

        proxy_tools = []
        for plugin_name, plugin in plugin_manager.plugins.items():
            for tool_def in plugin.tools:
                t_name = tool_def.get("name")
                t_desc = tool_def.get("description", f"Tool from {plugin_name} plugin")
                t_params = tool_def.get("parameters", {}).get("properties", {})

                # Create signature based on parameters
                sig_params = [inspect.Parameter('ctx', inspect.Parameter.POSITIONAL_OR_KEYWORD)]
                for p_name, p_info in t_params.items():
                    sig_params.append(inspect.Parameter(
                        p_name,
                        inspect.Parameter.KEYWORD_ONLY,
                        default=None if p_name not in tool_def.get("parameters", {}).get("required", []) else inspect.Parameter.empty
                    ))

                # Dynamic Proxy Function
                async def proxy_func(ctx, t_name=t_name, **kwargs):
                    # This will be called by LiveKit, we route it to tool_executor
                    return await tool_executor(t_name, kwargs)

                # Set metadata for LiveKit
                proxy_func.__name__ = t_name
                proxy_func.__doc__ = t_desc
                proxy_func.__signature__ = inspect.Signature(sig_params)

                decorated = function_tool()(proxy_func)
                proxy_tools.append(decorated)

        if hasattr(agent, '_tools') and isinstance(agent._tools, list):
            agent._tools.extend(proxy_tools)
            logger.info(f"✅ Registered {len(proxy_tools)} Proxy Tools from plugins")

        router.set_tool_executor(tool_executor)
        logger.info(f"✅ Router configured with {len(tool_map)} tools")
        
        return agent
