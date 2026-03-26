from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

def validate_tool_call(call: Any, available_tool_names: List[str]) -> bool:
    """
    Validates a tool call object from the LLM.
    
    Checks:
    1. Call is not None
    2. Function name exists in available_tools
    3. Arguments are a valid dictionary
    """
    if not call:
        return False

    # Extract function name
    func_name = ""
    if hasattr(call, 'function') and call.function:
        func_name = getattr(call.function, 'name', "")
    elif hasattr(call, 'name'):
        func_name = call.name
    
    if not func_name:
        logger.warning("❌ Tool call validation failed: Missing function name")
        return False

    # 1. Check if tool is allowed
    if func_name not in available_tool_names:
        logger.warning(f"❌ Tool call validation failed: '{func_name}' not in available tools {available_tool_names}")
        return False

    # Extract arguments
    args = None
    if hasattr(call, 'function') and call.function:
        args = getattr(call.function, 'arguments', "")
    elif hasattr(call, 'arguments'):
        args = call.arguments
        
    # 2. Require parsed arguments to be dict before execution
    if not isinstance(args, dict):
        logger.warning(
            f"❌ Tool call validation failed: arguments for '{func_name}' must be dict, got {type(args).__name__}"
        )
        return False

    return True
