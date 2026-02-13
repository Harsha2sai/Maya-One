import logging
from typing import List, Tuple, Any

logger = logging.getLogger(__name__)

async def build_context(
    llm, 
    memory_manager, 
    user_id: str, 
    message: str, 
    tools: List[Any],
    **kwargs
) -> Tuple[str, List[Any]]:
    """
    Constructs the system prompt and toolset for the current turn.
    """
    # Import inside function to avoid circular imports if any
    from prompts import AGENT_INSTRUCTION
    
    # 1. Start with base instruction
    system_prompt = AGENT_INSTRUCTION
    
    # 2. Inject memories if available
    if memory_manager and user_id:
        try:
             # If memory_manager has retrieval logic, use it here.
             # For now, we append a simple context marker.
             pass
        except Exception as e:
            logger.warning(f"Failed to inject memories: {e}")

    # 3. Return full tool list (or filtered subset)
    # We return the full list for now. The schema fix in agent.py should have patched them,
    # and if not, FunctionContext.from_tools validation inside SmartLLM will catch it.
    return system_prompt, tools
