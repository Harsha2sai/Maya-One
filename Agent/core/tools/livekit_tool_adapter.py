from livekit.agents import llm
import logging
from typing import Any, Callable, List, Union

def ensure_livekit_tool(tool: Any) -> Any:
    """
    Guarantees every tool becomes a LiveKit compatible tool.
    Accepts:
        - FunctionTool
        - RawFunctionTool
        - callable (auto-wrapped)
    
    Idempotent: If tool is already a FunctionTool, return it as-is.
    """
    # Check if it's already a LiveKit tool
    if isinstance(tool, (llm.FunctionTool, getattr(llm, "RawFunctionTool", type(None)))):
        return tool

    # If it's a callable, wrap it
    if callable(tool):
        return llm.FunctionTool.from_callable(tool)

    raise TypeError(f"Unsupported tool type: {type(tool)}")


def adapt_tool_list(tools: List[Any]) -> List[Any]:
    """Convert entire tool list safely and deduplicate by tool name.
    
    Idempotent: Safe to call multiple times on the same list.
    """
    seen_names = {}
    deduplicated = []
    
    logger = logging.getLogger(__name__)
    for tool in tools:
        # Skip None values
        if tool is None:
            continue
            
        wrapped_tool = ensure_livekit_tool(tool)
        
        # Extract tool name from various possible locations
        # Check info.name first (FunctionTool standard)
        tool_name = None
        if hasattr(wrapped_tool, 'info') and wrapped_tool.info:
            tool_name = getattr(wrapped_tool.info, 'name', None)
        if not tool_name:
            tool_name = (
                getattr(wrapped_tool, 'name', None) or
                getattr(wrapped_tool, '__name__', None) or
                (getattr(wrapped_tool.metadata, 'name', None) if hasattr(wrapped_tool, 'metadata') else None)
            )
        
        if tool_name:
            if tool_name not in seen_names:
                seen_names[tool_name] = wrapped_tool
                deduplicated.append(wrapped_tool)
                logger.info(f"✅ Adapter: Added tool '{tool_name}'")
            else:
                # Silently skip duplicates
                logger.debug(f"⏭️ Adapter: Skipping duplicate tool '{tool_name}'")
        else:
            # If we can't extract a name, include it anyway (LiveKit will handle it)
            logger.warning(f"⚠️ Adapter: Added unnamed tool {wrapped_tool}")
            deduplicated.append(wrapped_tool)
    
    # Final safety: even if we have duplicates in the list that our extraction missed,
    # do a final pass to ensure uniqueness using the same logic as the first pass
    final_tools = []
    final_seen = {}
    for t in deduplicated:
        # Get name using the same logic as the main loop
        t_name = None
        if hasattr(t, 'info') and t.info:
            t_name = getattr(t.info, 'name', None)
        if not t_name:
            t_name = (
                getattr(t, 'name', None) or
                getattr(t, '__name__', None) or
                (getattr(t.metadata, 'name', None) if hasattr(t, 'metadata') else None)
            )
        
        if t_name and t_name in final_seen:
            logger.warning(f"🧹 Final cleanup: removing duplicate '{t_name}'")
            continue
        final_tools.append(t)
        if t_name:
            final_seen[t_name] = t
    
    logger.info(f"📊 Adapter: Deduplicated {len(tools)} -> {len(final_tools)} tools")
    return final_tools
