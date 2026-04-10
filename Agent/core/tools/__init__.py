# Tools Module Init
# ToolManager and planning_tools are imported lazily to avoid pulling in the
# full runtime chain (MCP client, router, media agent, etc.) during unit tests.
# Import them explicitly where needed: from core.tools.tool_manager import ToolManager

def __getattr__(name):
    if name == "ToolManager":
        from .tool_manager import ToolManager
        return ToolManager
    if name == "register_planning_tool":
        from .planning_tools import register_planning_tool
        return register_planning_tool
    raise AttributeError(f"module 'core.tools' has no attribute {name!r}")

__all__ = ['ToolManager', 'register_planning_tool']
