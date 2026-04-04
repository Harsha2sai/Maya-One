import importlib

from core.tools.livekit_tool_adapter import adapt_tool_list

from tools import information as information_module
from tools.system import pc_control as pc_control_module

information = importlib.reload(information_module)
pc_control = importlib.reload(pc_control_module)

def test_livekit_tool_adapter_converts_tools():
    # web_search and file_write are likely simple wrappers or functions
    tools = [information.web_search, pc_control.file_write]

    safe = adapt_tool_list(tools)

    for t in safe:
        name = type(t).__name__
        # It should be FunctionTool (or RawFunctionTool)
        # In newer versions it might be FunctionTool
        assert "FunctionTool" in name, f"Bad tool: {name}"
        
        # Verify it has correct properties
        if hasattr(t, 'metadata'):
            assert t.metadata is not None
