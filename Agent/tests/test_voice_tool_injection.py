from core.tools.livekit_tool_adapter import adapt_tool_list
# Correct imports based on agent.py
from tools import web_search
from tools.system.pc_control import file_write

def test_livekit_tool_adapter_converts_tools():
    # web_search and file_write are likely simple wrappers or functions
    tools = [web_search, file_write]

    safe = adapt_tool_list(tools)

    for t in safe:
        name = type(t).__name__
        # It should be FunctionTool (or RawFunctionTool)
        # In newer versions it might be FunctionTool
        assert "FunctionTool" in name, f"Bad tool: {name}"
        
        # Verify it has correct properties
        if hasattr(t, 'metadata'):
            assert t.metadata is not None
