
from typing import Any, Dict, Optional
import logging
import json

logger = logging.getLogger(__name__)

class NormalizedToolCall:
    """Standardized tool call object for internal use."""
    def __init__(self, name: str, arguments: Dict[str, Any], call_id: str):
        self.name = name
        self.arguments = arguments
        self.call_id = call_id

    def __repr__(self):
        return f"NormalizedToolCall(name='{self.name}', args={self.arguments}, id='{self.call_id}')"

class ToolCallAdapter:
    """
    Adapts various SDK tool call formats (OpenAI old/new, LiveKit wrappers)
    into a single NormalizedToolCall.
    """

    @staticmethod
    def normalize(tool_call: Any) -> Optional[NormalizedToolCall]:
        """
        Normalize a tool call object or dict into NormalizedToolCall.
        Returns None if normalization fails.
        """
        try:
            name = ""
            arguments_str = ""
            call_id = ""

            # Check for dictionary
            if isinstance(tool_call, dict):
                # OpenAI Dict Format
                if "function" in tool_call:
                    func = tool_call["function"]
                    name = func.get("name", "")
                    arguments_str = func.get("arguments", "{}")
                elif "name" in tool_call: # Flattened or new format
                     name = tool_call.get("name", "")
                     arguments_str = tool_call.get("arguments", "{}")
                
                call_id = tool_call.get("id", "unknown")

            # Check for Object (LiveKit / OpenAI SDK objects)
            else:
                # Try new schema first (tool_call.name direct access)
                if hasattr(tool_call, "name"):
                     name = tool_call.name
                     arguments_str = getattr(tool_call, "arguments", "{}")
                
                # Try old schema (tool_call.function.name)
                elif hasattr(tool_call, "function"):
                     func = tool_call.function
                     name = getattr(func, "name", "")
                     arguments_str = getattr(func, "arguments", "{}")
                
                call_id = getattr(tool_call, "id", "unknown")

            if not name:
                logger.warning(f"ToolCallAdapter: Could not extract name from {tool_call}")
                return None

            # Parse JSON arguments if they are string
            arguments = {}
            if isinstance(arguments_str, str):
                try:
                    arguments = json.loads(arguments_str) if arguments_str.strip() else {}
                except json.JSONDecodeError:
                     logger.warning(f"ToolCallAdapter: Failed to parse arguments JSON for {name}: {arguments_str}")
                     # Fallback: maybe it's already a dict?
                     arguments = {}
            elif isinstance(arguments_str, dict):
                arguments = arguments_str
            
            return NormalizedToolCall(name=name, arguments=arguments, call_id=call_id)

        except Exception as e:
            logger.error(f"ToolCallAdapter: Error normalizing tool call: {e}")
            return None
