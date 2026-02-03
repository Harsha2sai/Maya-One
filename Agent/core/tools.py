import logging
import os
import asyncio
from typing import List, Any, Dict

from mcp_client.agent_tools import MCPToolsIntegration
from mcp_client.server import MCPServerSse
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
        
        async def tool_executor(name: str, params: dict) -> str:
            logger.info(f"🛠️ Executing tool: {name}")
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

        router.set_tool_executor(tool_executor)
        logger.info(f"✅ Router configured with {len(tool_map)} tools")
        
        return agent
