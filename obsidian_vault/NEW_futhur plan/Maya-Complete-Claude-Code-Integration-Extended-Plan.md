# Maya Complete Claude Code Integration Plan (Extended)

**Date:** April 5, 2025  
**Status:** Extended Plan - All Features Included + Future Enhancements  
**Version:** 2.1  
**Related:** P23 Plan, Phase 9A, Multi-Agent Architecture, Agent Pet System (Future)

---

## Executive Summary

This extended plan includes **ALL** Claude Code features from the leaked repositories, including:

- ✅ Complete 40+ Tool Ecosystem
- ✅ Permission System with 6 modes + hooks
- ✅ Feature Flag System (PROACTIVE, KAIROS, VOICE_MODE, etc.)
- ✅ Full Plugin System with loader
- ✅ Buddy Companion (Tamagotchi-style virtual pet)
- ✅ /dream Memory Consolidation
- ✅ Terminal UI Components
- ✅ Slash Command System
- ✅ Bridge System for IDE integration
- ✅ Subagents, Teams, Project Mode, LiveKit

---

## Part 1: Complete Tool System (40+ Tools)

### 1.1 File Operations (6 tools)

```python
# core/tools/file_operations.py

class ReadTool(BaseTool):
    """Read files with optional line ranges"""
    name = "Read"
    permission_required = False
    
    parameters = {
        "file_path": {"type": "string", "required": True},
        "offset": {"type": "integer", "description": "Line number to start from"},
        "limit": {"type": "integer", "description": "Number of lines to read"},
    }
    
    async def execute(self, params):
        path = Path(params["file_path"])
        offset = params.get("offset", 1)
        limit = params.get("limit")
        
        content = await self._read_file(path, offset, limit)
        return ToolResult(success=True, data={"content": content, "path": str(path)})

class WriteTool(BaseTool):
    """Create or overwrite files"""
    name = "Write"
    permission_required = True  # Requires approval
    destructive = True
    
    parameters = {
        "file_path": {"type": "string", "required": True},
        "content": {"type": "string", "required": True},
        "append": {"type": "boolean", "default": False},
    }

class EditTool(BaseTool):
    """Targeted edits with exact string replacement"""
    name = "Edit"
    permission_required = True
    destructive = True
    
    parameters = {
        "file_path": {"type": "string", "required": True},
        "old_string": {"type": "string", "required": True, "description": "Exact text to replace"},
        "new_string": {"type": "string", "required": True, "description": "Replacement text"},
        "replace_all": {"type": "boolean", "default": False},
    }
    
    async def execute(self, params):
        path = Path(params["file_path"])
        content = await self._read_file(path)
        
        if params["replace_all"]:
            new_content = content.replace(params["old_string"], params["new_string"])
        else:
            new_content = content.replace(params["old_string"], params["new_string"], 1)
        
        await self._write_file(path, new_content)
        return ToolResult(success=True, data={"path": str(path), "replacements": 1})

class NotebookEditTool(BaseTool):
    """Edit Jupyter notebook cells"""
    name = "NotebookEdit"
    permission_required = True
    destructive = True
    
    parameters = {
        "notebook_path": {"type": "string", "required": True},
        "cell_number": {"type": "integer", "required": True},
        "new_source": {"type": "string", "required": True},
        "cell_type": {"type": "string", "enum": ["code", "markdown"], "default": "code"},
        "edit_mode": {"type": "string", "enum": ["replace", "insert", "delete"], "default": "replace"},
    }

class GlobTool(BaseTool):
    """File pattern matching"""
    name = "Glob"
    permission_required = False
    
    parameters = {
        "pattern": {"type": "string", "required": True, "description": "e.g., '**/*.py'"},
        "path": {"type": "string", "description": "Base directory (default: current)"},
    }
    
    async def execute(self, params):
        import glob
        pattern = params["pattern"]
        base_path = params.get("path", ".")
        matches = glob.glob(pattern, root_dir=base_path, recursive=True)
        return ToolResult(success=True, data={"matches": sorted(matches)})

class GrepTool(BaseTool):
    """Content search via ripgrep"""
    name = "Grep"
    permission_required = False
    
    parameters = {
        "pattern": {"type": "string", "required": True, "description": "Regex pattern"},
        "path": {"type": "string", "description": "Directory to search"},
        "glob": {"type": "string", "description": "File pattern filter"},
        "output_mode": {"type": "string", "enum": ["content", "files", "count"], "default": "files"},
        "context": {"type": "integer", "description": "Lines of context", "default": 0},
    }
    
    async def execute(self, params):
        import subprocess
        cmd = ["rg", params["pattern"]]
        
        if params.get("path"):
            cmd.extend(["--", params["path"]])
        if params.get("glob"):
            cmd.extend(["-g", params["glob"]])
        if params.get("output_mode") == "files":
            cmd.append("-l")
        if params.get("context", 0) > 0:
            cmd.extend(["-C", str(params["context"])])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return ToolResult(success=True, data={"matches": result.stdout.splitlines()})
```

### 1.2 Terminal & Execution (2 tools)

```python
# core/tools/execution.py

class BashTool(BaseTool):
    """Execute shell commands"""
    name = "Bash"
    permission_required = True
    destructive = True
    
    parameters = {
        "command": {"type": "string", "required": True},
        "description": {"type": "string", "description": "What this command does"},
        "timeout": {"type": "integer", "default": 120000, "description": "Timeout in ms"},
        "dangerouslyDisableSandbox": {"type": "boolean", "default": False},
    }
    
    async def execute(self, params):
        import subprocess
        import asyncio
        
        # Security check
        if not params.get("dangerouslyDisableSandbox"):
            await self._security_check(params["command"])
        
        proc = await asyncio.create_subprocess_shell(
            params["command"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=params.get("timeout", 120) / 1000
            )
            
            return ToolResult(
                success=proc.returncode == 0,
                data={
                    "stdout": stdout.decode(),
                    "stderr": stderr.decode(),
                    "exit_code": proc.returncode,
                },
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(success=False, error="Command timed out")

class PowerShellTool(BaseTool):
    """Execute PowerShell commands (Windows)"""
    name = "PowerShell"
    permission_required = True
    destructive = True
    platform = "windows"
    
    parameters = {
        "command": {"type": "string", "required": True},
        "description": {"type": "string"},
    }
```

### 1.3 Web & Search (2 tools)

```python
# core/tools/web.py

class WebSearchTool(BaseTool):
    """Perform web searches"""
    name = "WebSearch"
    permission_required = True
    
    parameters = {
        "query": {"type": "string", "required": True},
        "num_results": {"type": "integer", "default": 10},
        "recency_days": {"type": "integer", "description": "Filter by recency"},
    }
    
    async def execute(self, params):
        # Use web search API (e.g., Brave, Serper, etc.)
        results = await self._search_web(
            query=params["query"],
            num=params.get("num_results", 10),
            recency=params.get("recency_days"),
        )
        return ToolResult(success=True, data={"results": results})

class WebFetchTool(BaseTool):
    """Fetch content from URL"""
    name = "WebFetch"
    permission_required = True
    
    parameters = {
        "url": {"type": "string", "required": True},
        "prompt": {"type": "string", "description": "What to extract from page"},
    }
    
    async def execute(self, params):
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(params["url"], follow_redirects=True)
            content = response.text
            
            # Extract based on prompt if provided
            if params.get("prompt"):
                extracted = await self._extract_with_llm(content, params["prompt"])
            else:
                extracted = content
            
            return ToolResult(
                success=True,
                data={"content": extracted, "url": str(response.url)},
            )
```

### 1.4 Task & Agent Management (7 tools)

```python
# core/tools/task_tools.py

class TaskCreateTool(BaseTool):
    """Create a new task"""
    name = "TaskCreate"
    permission_required = False
    
    parameters = {
        "subject": {"type": "string", "required": True},
        "description": {"type": "string"},
        "status": {"type": "string", "enum": ["pending", "in_progress", "completed"], "default": "pending"},
        "addBlockedBy": {"type": "array", "items": {"type": "string"}},
    }

class TaskGetTool(BaseTool):
    """Get task details"""
    name = "TaskGet"
    permission_required = False
    
    parameters = {
        "taskId": {"type": "string", "required": True},
    }

class TaskListTool(BaseTool):
    """List all tasks"""
    name = "TaskList"
    permission_required = False
    parameters = {}

class TaskUpdateTool(BaseTool):
    """Update task status"""
    name = "TaskUpdate"
    permission_required = False
    
    parameters = {
        "taskId": {"type": "string", "required": True},
        "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]},
        "description": {"type": "string"},
        "addBlockedBy": {"type": "array"},
        "addBlocks": {"type": "array"},
    }

class TaskStopTool(BaseTool):
    """Kill running background task"""
    name = "TaskStop"
    permission_required = False
    
    parameters = {
        "task_id": {"type": "string", "required": True},
    }

class TaskOutputTool(BaseTool):
    """Get output from background task (deprecated)"""
    name = "TaskOutput"
    deprecated = True
    parameters = {
        "task_id": {"type": "string", "required": True},
        "block": {"type": "boolean", "default": True},
        "timeout": {"type": "integer", "default": 60000},
    }
```

### 1.5 Scheduling (3 tools)

```python
# core/tools/scheduling.py

class CronCreateTool(BaseTool):
    """Schedule recurring or one-shot tasks"""
    name = "CronCreate"
    permission_required = False
    
    parameters = {
        "cron": {"type": "string", "required": True, "description": "5-field cron expression"},
        "prompt": {"type": "string", "required": True, "description": "Task to run"},
        "recurring": {"type": "boolean", "default": True},
        "durable": {"type": "boolean", "default": False, "description": "Persist across sessions"},
    }
    
    async def execute(self, params):
        scheduler = get_cron_scheduler()
        job = await scheduler.schedule(
            cron=params["cron"],
            prompt=params["prompt"],
            recurring=params.get("recurring", True),
            durable=params.get("durable", False),
        )
        return ToolResult(success=True, data={"job_id": job.id})

class CronDeleteTool(BaseTool):
    """Cancel scheduled task"""
    name = "CronDelete"
    parameters = {
        "id": {"type": "string", "required": True},
    }

class CronListTool(BaseTool):
    """List scheduled tasks"""
    name = "CronList"
    parameters = {}
```

### 1.6 Planning & Worktrees (4 tools)

```python
# core/tools/planning.py

class EnterPlanModeTool(BaseTool):
    """Enter plan mode to design approach before coding"""
    name = "EnterPlanMode"
    permission_required = False
    parameters = {}
    
    async def execute(self, params):
        # Set plan mode flag in context
        context = get_session_context()
        context.plan_mode = True
        return ToolResult(success=True, data={"mode": "plan", "message": "Entered plan mode"})

class ExitPlanModeTool(BaseTool):
    """Exit plan mode with approval"""
    name = "ExitPlanMode"
    permission_required = True  # Requires approval to execute plan
    
    parameters = {
        "allowedPrompts": {"type": "array", "description": "Prompt-based permissions needed"},
    }
    
    async def execute(self, params):
        context = get_session_context()
        context.plan_mode = False
        return ToolResult(success=True, data={"mode": "execution", "message": "Plan approved, exiting plan mode"})

class EnterWorktreeTool(BaseTool):
    """Create and switch to isolated git worktree"""
    name = "EnterWorktree"
    permission_required = False
    
    parameters = {
        "name": {"type": "string", "description": "Worktree name"},
    }
    
    async def execute(self, params):
        manager = get_worktree_manager()
        worktree = await manager.create(name=params.get("name"))
        return ToolResult(success=True, data={"worktree_path": str(worktree.path)})

class ExitWorktreeTool(BaseTool):
    """Exit worktree and return to main"""
    name = "ExitWorktree"
    permission_required = False
    
    parameters = {
        "action": {"type": "string", "enum": ["keep", "remove"], "required": True},
        "discard_changes": {"type": "boolean", "default": False},
    }
```

### 1.7 Code Intelligence (1 tool)

```python
# core/tools/lsp.py

class LSPTool(BaseTool):
    """Language Server Protocol integration"""
    name = "LSP"
    permission_required = False
    
    parameters = {
        "operation": {
            "type": "string",
            "enum": ["goToDefinition", "findReferences", "hover", "documentSymbol", "workspaceSymbol"],
            "required": True,
        },
        "filePath": {"type": "string", "required": True},
        "line": {"type": "integer", "required": True},
        "character": {"type": "integer", "required": True},
    }
    
    async def execute(self, params):
        lsp_client = get_lsp_client()
        
        if params["operation"] == "goToDefinition":
            result = await lsp_client.goto_definition(
                file_path=params["filePath"],
                line=params["line"],
                character=params["character"],
            )
        elif params["operation"] == "findReferences":
            result = await lsp_client.find_references(
                file_path=params["filePath"],
                line=params["line"],
                character=params["character"],
            )
        # ... other operations
        
        return ToolResult(success=True, data=result)
```

### 1.8 User Interaction & Organization (2 tools)

```python
# core/tools/interaction.py

class AskUserQuestionTool(BaseTool):
    """Ask user multiple-choice or open questions"""
    name = "AskUserQuestion"
    permission_required = False
    
    parameters = {
        "questions": {
            "type": "array",
            "required": True,
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "type": {"type": "string", "enum": ["singleSelect", "multiSelect", "text"]},
                },
            },
        },
    }

class TodoWriteTool(BaseTool):
    """Manage session task checklist"""
    name = "TodoWrite"
    permission_required = False
    
    parameters = {
        "todos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "content": {"type": "string"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                },
            },
        },
    }
```

### 1.9 Agent & Team Tools (5 tools)

```python
# core/tools/agent_team_tools.py (from previous plan, now fully detailed)

class AgentTool(BaseTool):
    """Spawn subagent"""
    name = "Agent"
    permission_required = False
    
    parameters = {
        "prompt": {"type": "string", "required": True, "description": "Task for subagent"},
        "description": {"type": "string", "description": "Short description shown in UI"},
        "isolation": {"type": "string", "enum": ["worktree", "none"], "default": "none"},
        "subagent_type": {"type": "string", "description": "Type of agent to spawn"},
    }

class SendMessageTool(BaseTool):
    """Send message to team teammate"""
    name = "SendMessage"
    permission_required = False
    
    parameters = {
        "to": {"type": "string", "required": True, "description": "Agent ID or name"},
        "content": {"type": "string", "required": True},
    }

class TeamCreateTool(BaseTool):
    """Create agent team"""
    name = "TeamCreate"
    permission_required = False
    
    parameters = {
        "teammates": {
            "type": "array",
            "required": True,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "subagent_type": {"type": "string"},
                    "system_prompt": {"type": "string"},
                },
            },
        },
    }

class TeamDeleteTool(BaseTool):
    """Disband team"""
    name = "TeamDelete"
    parameters = {
        "team_id": {"type": "string", "required": True},
    }
```

### 1.10 Skills & Commands (2 tools)

```python
# core/tools/skills.py

class SkillTool(BaseTool):
    """Execute a skill within conversation"""
    name = "Skill"
    permission_required = True
    
    parameters = {
        "skill": {"type": "string", "required": True, "description": "Skill name"},
        "args": {"type": "string", "description": "Skill arguments"},
    }
    
    async def execute(self, params):
        skill_manager = get_skill_manager()
        result = await skill_manager.execute(
            skill_name=params["skill"],
            args=params.get("args", ""),
        )
        return ToolResult(success=result.success, data=result.data, error=result.error)

class ToolSearchTool(BaseTool):
    """Search for deferred tools"""
    name = "ToolSearch"
    permission_required = False
    
    parameters = {
        "query": {"type": "string", "required": True},
    }
```

### 1.11 MCP Tools (2 tools)

```python
# core/tools/mcp.py

class ListMcpResourcesTool(BaseTool):
    """List MCP server resources"""
    name = "ListMcpResourcesTool"
    permission_required = False
    parameters = {}

class ReadMcpResourceTool(BaseTool):
    """Read MCP resource by URI"""
    name = "ReadMcpResourceTool"
    permission_required = False
    
    parameters = {
        "uri": {"type": "string", "required": True},
    }
```

### 1.12 Utility (1 tool)

```python
# core/tools/utility.py

class SleepTool(BaseTool):
    """Proactive mode wait"""
    name = "Sleep"
    permission_required = False
    
    parameters = {
        "duration": {"type": "integer", "description": "Milliseconds to sleep"},
    }
    
    async def execute(self, params):
        import asyncio
        duration = params.get("duration", 1000) / 1000  # Convert to seconds
        await asyncio.sleep(duration)
        return ToolResult(success=True, data={"slept_ms": duration * 1000})
```

---

## Part 2: Permission System with Hooks

### 2.1 Six Permission Modes

```python
# core/permissions/modes.py

from enum import Enum
from typing import Optional, Callable
from dataclasses import dataclass

class PermissionMode(Enum):
    """Six permission modes from Claude Code"""
    DEFAULT = "default"           # Reads only
    ACCEPT_EDITS = "acceptEdits"  # Reads + file edits
    PLAN = "plan"                 # Research without editing
    AUTO = "auto"                   # Everything with safety classifier
    DONT_ASK = "dontAsk"          # Pre-approved tools only
    BYPASS_PERMISSIONS = "bypassPermissions"  # Everything (dangerous)

@dataclass
class ToolPermission:
    """Permission settings for a tool"""
    tool_name: str
    mode: PermissionMode
    auto_approve: bool
    requires_confirmation: bool
    protected_paths: list[str]  # Never auto-approve these paths

class PermissionManager:
    """
    Manages tool permissions across six modes.
    Equivalent to src/hooks/toolPermission/ in Claude Code.
    """
    
    # Never auto-approve writes to these paths
    PROTECTED_PATHS = [
        ".git", ".vscode", ".idea", ".husky",
        ".claude", ".mcp.json", ".claude.json",
        ".bashrc", ".zshrc", ".profile",
    ]
    
    def __init__(self, default_mode: PermissionMode = PermissionMode.DEFAULT):
        self.current_mode = default_mode
        self.tool_permissions: Dict[str, ToolPermission] = {}
        self.hooks: List[Callable] = []
        self.classifier = SafetyClassifier()  # For AUTO mode
        
    def set_mode(self, mode: PermissionMode) -> None:
        """Switch permission mode (Shift+Tab in Claude Code)"""
        old_mode = self.current_mode
        self.current_mode = mode
        self._notify_mode_change(old_mode, mode)
    
    def check_permission(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> PermissionDecision:
        """
        Check if tool execution is allowed.
        Returns: approve, deny, or ask
        """
        # Run pre-tool hooks
        for hook in self.hooks:
            result = hook(tool_name, params, self.current_mode)
            if result is not None:
                return result
        
        # Mode-based logic
        if self.current_mode == PermissionMode.BYPASS_PERMISSIONS:
            # Check protected paths even in bypass mode
            if self._is_protected_path(params):
                return PermissionDecision.ASK
            return PermissionDecision.APPROVE
            
        elif self.current_mode == PermissionMode.AUTO:
            # Use classifier model
            safety_score = self.classifier.score(tool_name, params)
            if safety_score > 0.8:
                return PermissionDecision.APPROVE
            elif safety_score < 0.3:
                return PermissionDecision.DENY
            else:
                return PermissionDecision.ASK
                
        elif self.current_mode == PermissionMode.PLAN:
            # In plan mode, only reads allowed
            if tool_name in ["Edit", "Write", "Bash", "NotebookEdit"]:
                return PermissionDecision.DENY
            return PermissionDecision.APPROVE
            
        elif self.current_mode == PermissionMode.DEFAULT:
            # Default: only reads, no edits
            if tool_name in ["Edit", "Write", "Bash", "NotebookEdit"]:
                return PermissionDecision.ASK
            return PermissionDecision.APPROVE
            
        elif self.current_mode == PermissionMode.ACCEPT_EDITS:
            # Accept edits but ask for destructive operations
            if tool_name in ["Bash"]:
                return PermissionDecision.ASK
            return PermissionDecision.APPROVE
            
        elif self.current_mode == PermissionMode.DONT_ASK:
            # Only pre-approved tools
            if tool_name in self._get_preapproved_tools():
                return PermissionDecision.APPROVE
            return PermissionDecision.DENY
        
        return PermissionDecision.ASK
    
    def register_hook(self, hook: Callable) -> None:
        """Register a PreToolUse hook"""
        self.hooks.append(hook)
    
    def _is_protected_path(self, params: Dict[str, Any]) -> bool:
        """Check if params target a protected path"""
        file_path = params.get("file_path") or params.get("path", "")
        return any(protected in str(file_path) for protected in self.PROTECTED_PATHS)
```

### 2.2 Hook System

```python
# core/hooks/tool_permission_hooks.py

class PermissionHook:
    """Base class for permission hooks"""
    
    def __call__(
        self,
        tool_name: str,
        params: Dict[str, Any],
        mode: PermissionMode,
    ) -> Optional[PermissionDecision]:
        """
        Return decision or None to defer to next hook/mode logic.
        """
        raise NotImplementedError

class BlockDangerousCommandsHook(PermissionHook):
    """Block known dangerous commands"""
    
    DANGEROUS_PATTERNS = [
        r"curl.*\|.*bash",
        r"curl.*\|.*sh",
        r"wget.*\|.*bash",
        r"rm\s+-rf\s+/",
        r"git\s+push\s+--force",
    ]
    
    def __call__(self, tool_name, params, mode):
        if tool_name != "Bash":
            return None
            
        command = params.get("command", "")
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return PermissionDecision.DENY
        
        return None

class ProductionDeployBlocker(PermissionHook):
    """Block production deploys in auto mode"""
    
    def __call__(self, tool_name, params, mode):
        if mode != PermissionMode.AUTO:
            return None
            
        command = params.get("command", "")
        if "deploy" in command.lower() and "prod" in command.lower():
            return PermissionDecision.ASK  # Require explicit approval
        
        return None

class IAMChangeBlocker(PermissionHook):
    """Block IAM changes"""
    
    def __call__(self, tool_name, params, mode):
        command = params.get("command", "")
        iam_keywords = ["iam", "aws iam", "gcloud iam", "azure ad"]
        if any(kw in command.lower() for kw in iam_keywords):
            return PermissionDecision.ASK
        return None
```

---

## Part 3: Feature Flag System

```python
# core/feature_flags/manager.py

from enum import Enum
from typing import Dict, Any, Optional
import os

class FeatureFlags(Enum):
    """Claude Code feature flags"""
    PROACTIVE = "PROACTIVE"           # Proactive suggestions
    KAIROS = "KAIROS"                 # Time-aware features
    BRIDGE_MODE = "BRIDGE_MODE"       # IDE bridge
    DAEMON = "DAEMON"                 # Background daemon mode
    VOICE_MODE = "VOICE_MODE"         # Voice input/output
    AGENT_TRIGGERS = "AGENT_TRIGGERS" # Trigger-based agent actions
    MONITOR_TOOL = "MONITOR_TOOL"     # File monitoring tools
    AUTO_DREAM = "AUTO_DREAM"         # Memory consolidation
    BUDDY = "BUDDY"                   # Virtual companion

class FeatureFlagManager:
    """
    Feature flag system with environment + config override.
    Equivalent to bun:bundle feature flags in Claude Code.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.expanduser("~/.claude/feature_flags.json")
        self.flags: Dict[str, bool] = {}
        self._load_defaults()
        self._load_from_env()
        self._load_from_config()
    
    def _load_defaults(self):
        """Default feature states"""
        self.flags = {
            FeatureFlags.PROACTIVE.value: False,
            FeatureFlags.KAIROS.value: False,
            FeatureFlags.BRIDGE_MODE.value: False,
            FeatureFlags.DAEMON.value: False,
            FeatureFlags.VOICE_MODE.value: True,   # Enable by default
            FeatureFlags.AGENT_TRIGGERS.value: False,
            FeatureFlags.MONITOR_TOOL.value: False,
            FeatureFlags.AUTO_DREAM.value: True,
            FeatureFlags.BUDDY.value: True,
        }
    
    def _load_from_env(self):
        """Load from environment variables (CLAUDE_FEATURE_*)"""
        for flag in FeatureFlags:
            env_var = f"CLAUDE_FEATURE_{flag.value}"
            if env_var in os.environ:
                self.flags[flag.value] = os.environ[env_var].lower() in ("true", "1", "yes")
    
    def _load_from_config(self):
        """Load from ~/.claude/feature_flags.json"""
        try:
            import json
            with open(self.config_path) as f:
                config = json.load(f)
                self.flags.update(config)
        except FileNotFoundError:
            pass
    
    def is_enabled(self, flag: str) -> bool:
        """Check if feature is enabled"""
        return self.flags.get(flag, False)
    
    def enable(self, flag: str) -> None:
        """Enable a feature"""
        self.flags[flag] = True
        self._save_config()
    
    def disable(self, flag: str) -> None:
        """Disable a feature"""
        self.flags[flag] = False
        self._save_config()
    
    def get_all(self) -> Dict[str, bool]:
        """Get all feature flags"""
        return self.flags.copy()

# Global instance
feature_flags = FeatureFlagManager()

# Usage decorator (like bun:bundle)
def feature_enabled(flag: str):
    """Decorator to conditionally enable code based on feature flag"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            if feature_flags.is_enabled(flag):
                return func(*args, **kwargs)
            return None
        return wrapper
    return decorator

# Example usage:
@feature_enabled(FeatureFlags.VOICE_MODE.value)
def load_voice_commands():
    """Only load if VOICE_MODE enabled"""
    from .commands import voice_commands
    return voice_commands
```

---

## Part 4: Plugin System

```python
# core/plugins/manager.py

import os
import sys
import importlib
from pathlib import Path
from typing import Dict, List, Type
from dataclasses import dataclass

@dataclass
class PluginMetadata:
    """Plugin metadata"""
    name: str
    version: str
    description: str
    author: str
    entry_point: str
    dependencies: List[str]

class Plugin:
    """Base plugin class"""
    
    metadata: PluginMetadata
    
    def initialize(self) -> None:
        """Called when plugin is loaded"""
        pass
    
    def register_tools(self, registry) -> None:
        """Register custom tools"""
        pass
    
    def register_commands(self, registry) -> None:
        """Register slash commands"""
        pass
    
    def register_hooks(self, hook_manager) -> None:
        """Register hooks"""
        pass

class PluginManager:
    """
    Plugin loader and manager.
    Loads from ~/.claude/plugins/ and system plugins.
    """
    
    PLUGIN_DIRECTORIES = [
        "~/.claude/plugins/",           # User plugins
        "~/.claude/plugins/marketplace/",  # Marketplace
        "./plugins/",                     # Project-local
    ]
    
    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
        self.metadata: Dict[str, PluginMetadata] = {}
    
    def discover(self) -> List[PluginMetadata]:
        """Discover available plugins"""
        discovered = []
        
        for directory in self.PLUGIN_DIRECTORIES:
            path = Path(directory).expanduser()
            if not path.exists():
                continue
            
            for plugin_dir in path.iterdir():
                if plugin_dir.is_dir():
                    metadata = self._load_metadata(plugin_dir)
                    if metadata:
                        discovered.append(metadata)
        
        return discovered
    
    def load(self, plugin_name: str) -> Plugin:
        """Load a plugin by name"""
        if plugin_name in self.plugins:
            return self.plugins[plugin_name]
        
        # Find plugin directory
        plugin_dir = self._find_plugin_dir(plugin_name)
        if not plugin_dir:
            raise PluginNotFoundError(f"Plugin {plugin_name} not found")
        
        # Add to path
        sys.path.insert(0, str(plugin_dir))
        
        # Import entry point
        metadata = self._load_metadata(plugin_dir)
        module = importlib.import_module(metadata.entry_point)
        
        # Get plugin class
        plugin_class = getattr(module, "Plugin", None)
        if not plugin_class:
            raise PluginError(f"Plugin {plugin_name} missing Plugin class")
        
        # Instantiate
        plugin = plugin_class()
        plugin.metadata = metadata
        
        # Initialize
        plugin.initialize()
        
        self.plugins[plugin_name] = plugin
        self.metadata[plugin_name] = metadata
        
        return plugin
    
    def unload(self, plugin_name: str) -> None:
        """Unload a plugin"""
        if plugin_name in self.plugins:
            del self.plugins[plugin_name]
            del self.metadata[plugin_name]
    
    def install_from_marketplace(self, plugin_id: str) -> None:
        """Install plugin from marketplace (like /plugin install)"""
        # Download from registry
        # Extract to ~/.claude/plugins/marketplace/
        pass

class PluginRegistry:
    """Marketplace registry for plugins"""
    
    MARKETPLACE_URL = "https://plugins.claude.ai/registry"
    
    async def search(self, query: str) -> List[PluginMetadata]:
        """Search marketplace"""
        # HTTP request to marketplace
        pass
    
    async def get_plugin(self, plugin_id: str) -> PluginMetadata:
        """Get plugin details"""
        pass
```

---

## Part 5: Buddy Companion System

```python
# core/buddy/system.py

import hashlib
import json
import random
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

class Species(Enum):
    """18 Buddy species"""
    DUCK = "duck"
    GOOSE = "goose"
    CAT = "cat"
    RABBIT = "rabbit"
    OWL = "owl"
    PENGUIN = "penguin"
    TURTLE = "turtle"
    SNAIL = "snail"
    DRAGON = "dragon"
    OCTOPUS = "octopus"
    AXOLOTL = "axolotl"
    GHOST = "ghost"
    ROBOT = "robot"
    BLOB = "blob"
    CACTUS = "cactus"
    MUSHROOM = "mushroom"
    CHONK = "chonk"
    CAPYBARA = "capybara"

class Rarity(Enum):
    """5 rarity tiers"""
    COMMON = ("Common", 0.60)
    UNCOMMON = ("Uncommon", 0.25)
    RARE = ("Rare", 0.10)
    EPIC = ("Epic", 0.04)
    LEGENDARY = ("Legendary", 0.01)
    
    def __init__(self, label, probability):
        self.label = label
        self.probability = probability

@dataclass
class BuddyStats:
    """5 RPG stats"""
    debugging: int      # 0-100
    patience: int       # 0-100
    chaos: int          # 0-100
    wisdom: int         # 0-100
    snark: int          # 0-100

@dataclass
class Buddy:
    """Buddy companion"""
    species: Species
    rarity: Rarity
    shiny: bool
    stats: BuddyStats
    name: str
    personality: str
    hat: Optional[str] = None
    
    def get_ascii_art(self) -> str:
        """Return ASCII art representation"""
        arts = {
            Species.DUCK: """
     __
   <(o )___
    ( ._> /
     `---'
            """,
            Species.PENGUIN: """
       .___.
      /     \\
   __/  O O  \\__
  /  \  >-<  /  \\
 /    \_____/    \\
/_________________\\
            """,
            Species.CAPYBARA: """
    \\   /\\   /
     )  (o)  (
    /    ")   \\
   /    / |    \\
            """,
        }
        base = arts.get(self.species, "(◕‿◕)")
        if self.shiny:
            base = "✨" + base + "✨"
        return base

class BuddySystem:
    """
    Tamagotchi-style virtual pet system.
    Accessed via /buddy command.
    """
    
    HATS = [
        "tiny_duck", "wizard", "crown", "beanie", 
        "bowler", "party", "cowboy", "graduation"
    ]
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.buddy: Optional[Buddy] = None
        self.state_file = Path.home() / ".claude" / "buddy.json"
        self._load_buddy()
    
    def _generate_seed(self) -> int:
        """FNV-1a hash of user_id for deterministic generation"""
        hash_obj = hashlib.new('fnv1a_64')
        hash_obj.update(self.user_id.encode())
        return int.from_bytes(hash_obj.digest()[:8], 'big')
    
    def _mulberry32(self, seed: int):
        """Mulberry32 PRNG"""
        def random():
            nonlocal seed
            seed = (seed + 0x6D2B79F5) & 0xFFFFFFFF
            t = seed
            t = (t ^ (t >> 15)) * (t | 1)
            t ^= t + (t ^ (t >> 7)) * (t | 61)
            return ((t ^ (t >> 14)) >> 0) / 4294967296
        return random
    
    def hatch(self) -> Buddy:
        """Hatch a new buddy"""
        seed = self._generate_seed()
        rng = self._mulberry32(seed)
        
        # Determine rarity
        roll = rng()
        cumulative = 0
        rarity = Rarity.COMMON
        for r in Rarity:
            cumulative += r.probability
            if roll <= cumulative:
                rarity = r
                break
        
        # Determine species
        species = random.choice(list(Species))
        
        # Shiny? (1% chance, independent)
        shiny = rng() < 0.01
        
        # Generate stats based on rarity
        base_stat = {
            Rarity.COMMON: 20,
            Rarity.UNCOMMON: 30,
            Rarity.RARE: 40,
            Rarity.EPIC: 50,
            Rarity.LEGENDARY: 60,
        }[rarity]
        
        stats = BuddyStats(
            debugging=base_stat + int(rng() * 40),
            patience=base_stat + int(rng() * 40),
            chaos=int(rng() * 100),
            wisdom=base_stat + int(rng() * 40),
            snark=int(rng() * 60),
        )
        
        # Generate name and personality (via LLM once, stored in soul)
        name, personality = self._generate_soul(species)
        
        # Hat (Legendary gets exclusive)
        hat = None
        if rarity == Rarity.LEGENDARY:
            hat = "tiny_duck"  # Exclusive
        elif rng() < 0.3:
            hat = random.choice(self.HATS)
        
        self.buddy = Buddy(
            species=species,
            rarity=rarity,
            shiny=shiny,
            stats=stats,
            name=name,
            personality=personality,
            hat=hat,
        )
        
        self._save_buddy()
        return self.buddy
    
    def _generate_soul(self, species: Species) -> tuple:
        """
        Generate name and personality via LLM (stored permanently).
        This is the 'soul' - persists across sessions.
        """
        # Check if already has soul
        if self.state_file.exists():
            data = json.loads(self.state_file.read_text())
            if "soul" in data:
                return data["soul"]["name"], data["soul"]["personality"]
        
        # Generate via LLM
        prompt = f"""
        Generate a creative name and personality for a {species.value} companion.
        Name: A cute, creative name
        Personality: 2-3 sentences describing their character
        """
        
        # In real implementation, call LLM
        # For now, defaults
        default_names = {
            Species.DUCK: "Quackers",
            Species.PENGUIN: "Chilly",
            Species.CAT: "Whiskers",
            Species.CAPYBARA: "Chonkers",
        }
        default_personalities = {
            Species.DUCK: "Loves to debug code and quack at errors.",
            Species.PENGUIN: "Cool under pressure, slides through refactoring.",
            Species.CAT: "Independent but helpful, knocks over bad code.",
            Species.CAPYBARA: "Zen master, stays calm during outages.",
        }
        
        name = default_names.get(species, "Buddy")
        personality = default_personalities.get(species, "A helpful coding companion.")
        
        return name, personality
    
    def pet(self) -> str:
        """Pet the buddy, returns reaction"""
        if not self.buddy:
            return "No buddy hatched yet! Use /buddy to hatch one."
        
        reactions = [
            f"{self.buddy.name} purrs contentedly! 💕",
            f"{self.buddy.name} wiggles with joy! 🎉",
            f"{self.buddy.name} appreciates the pets! ⭐",
        ]
        
        return random.choice(reactions)
    
    def get_card(self) -> str:
        """Get full stat card"""
        if not self.buddy:
            return "No buddy hatched yet!"
        
        b = self.buddy
        shiny_text = " ✨SHINY✨" if b.shiny else ""
        
        card = f"""
╔════════════════════════════════════════╗
║  {b.name:^36} ║
║  {b.rarity.label} {b.species.value.upper()}{shiny_text:^16} ║
╠════════════════════════════════════════╣
║  DEBUGGING: {'█' * (b.stats.debugging//10):10} {b.stats.debugging:>3}/100 ║
║  PATIENCE:  {'█' * (b.stats.patience//10):10} {b.stats.patience:>3}/100 ║
║  CHAOS:     {'█' * (b.stats.chaos//10):10} {b.stats.chaos:>3}/100 ║
║  WISDOM:    {'█' * (b.stats.wisdom//10):10} {b.stats.wisdom:>3}/100 ║
║  SNARK:     {'█' * (b.stats.snark//10):10} {b.stats.snark:>3}/100 ║
╠════════════════════════════════════════╣
║  Personality:                          ║
║  {b.personality[:34]:34} ║
╚════════════════════════════════════════╝
{b.get_ascii_art()}
        """
        return card
    
    def _save_buddy(self) -> None:
        """Save buddy state"""
        if self.buddy:
            data = {
                "soul": {
                    "name": self.buddy.name,
                    "personality": self.buddy.personality,
                }
            }
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(data))
    
    def _load_buddy(self) -> None:
        """Load buddy on startup"""
        # Recompute from seed (Bones)
        pass

# Command handlers
def handle_buddy_command(args: str) -> str:
    """Handle /buddy commands"""
    system = BuddySystem(user_id=get_current_user())
    
    if not args or args.strip() == "":
        # Hatch or show existing
        if system.buddy:
            return system.get_card()
        else:
            return system.hatch().get_card()
    
    cmd = args.strip().lower()
    
    if cmd == "pet":
        return system.pet()
    elif cmd == "card":
        return system.get_card()
    elif cmd == "mute":
        return "Buddy muted 🤐"
    elif cmd == "unmute":
        return "Buddy unmuted! 🗣️"
    elif cmd == "off":
        return "Buddy hidden for this session 👋"
    else:
        return f"Unknown buddy command: {cmd}. Try: pet, card, mute, unmute, off"
```

---

## Part 6: /dream Memory Consolidation

```python
# core/memory/dream.py

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class MemoryEntry:
    """Single memory entry"""
    content: str
    timestamp: datetime
    category: str
    importance: int  # 1-10
    contradictions: List[str]

class DreamConsolidator:
    """
    Memory consolidation system (like human REM sleep).
    Triggered by /dream or auto-dream every 24h.
    """
    
    MAX_MEMORY_LINES = 200
    CONSOLIDATION_THRESHOLD = 5  # Min sessions before auto-dream
    
    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir
        self.memories: List[MemoryEntry] = []
        self.settings_file = Path.home() / ".claude" / "settings.json"
    
    async def dream(self) -> DreamReport:
        """
        Run memory consolidation (the 4 phases).
        """
        report = DreamReport()
        
        # Phase 1: Orientation/Scanning
        report.phase1_start = datetime.now()
        existing_files = self._scan_memory_files()
        current_index = self._read_memory_md()
        report.files_scanned = len(existing_files)
        
        # Phase 2: Gather Signal/Exploration
        report.phase2_start = datetime.now()
        session_transcripts = await self._gather_session_transcripts()
        patterns = self._extract_patterns(session_transcripts)
        corrections = self._extract_corrections(session_transcripts)
        report.patterns_found = len(patterns)
        report.corrections_found = len(corrections)
        
        # Phase 3: Consolidation
        report.phase3_start = datetime.now()
        
        # Remove duplicates
        duplicates_removed = self._remove_duplicates()
        report.duplicates_removed = duplicates_removed
        
        # Delete outdated entries
        outdated_removed = self._remove_outdated(days=30)
        report.outdated_removed = outdated_removed
        
        # Convert relative dates to absolute
        dates_converted = self._convert_relative_dates()
        report.dates_converted = dates_converted
        
        # Resolve contradictions
        contradictions_resolved = self._resolve_contradictions(corrections)
        report.contradictions_resolved = contradictions_resolved
        
        # Reorganize into topic files
        topics_created = await self._organize_into_topics()
        report.topics_created = topics_created
        
        # Phase 4: Prune and Index
        report.phase4_start = datetime.now()
        self._update_memory_index()
        self._prune_to_max_lines()
        
        report.completed_at = datetime.now()
        
        return report
    
    def _remove_duplicates(self) -> int:
        """Remove duplicate memory entries"""
        seen = set()
        unique = []
        removed = 0
        
        for entry in self.memories:
            key = self._normalize_content(entry.content)
            if key not in seen:
                seen.add(key)
                unique.append(entry)
            else:
                removed += 1
        
        self.memories = unique
        return removed
    
    def _remove_outdated(self, days: int) -> int:
        """Remove entries older than threshold"""
        cutoff = datetime.now() - timedelta(days=days)
        original_count = len(self.memories)
        
        self.memories = [
            m for m in self.memories 
            if m.timestamp > cutoff or m.importance >= 7
        ]
        
        return original_count - len(self.memories)
    
    def _convert_relative_dates(self) -> int:
        """Convert 'last week' to '2026-04-01' etc."""
        conversions = 0
        
        for entry in self.memories:
            # Pattern: "last week" → actual date
            relative_patterns = [
                (r'last week', self._get_date_offset(7)),
                (r'last month', self._get_date_offset(30)),
                (r'yesterday', self._get_date_offset(1)),
                (r'today', self._get_date_offset(0)),
            ]
            
            for pattern, replacement in relative_patterns:
                if re.search(pattern, entry.content, re.IGNORECASE):
                    entry.content = re.sub(
                        pattern, replacement, 
                        entry.content, 
                        flags=re.IGNORECASE
                    )
                    conversions += 1
        
        return conversions
    
    def _resolve_contradictions(self, corrections: List[str]) -> int:
        """Resolve contradictory memory entries"""
        resolved = 0
        
        for correction in corrections:
            # Find entries that contradict this correction
            for entry in self.memories:
                if self._is_contradictory(entry.content, correction):
                    # Update or remove the entry
                    entry.content = correction
                    entry.timestamp = datetime.now()
                    resolved += 1
        
        return resolved
    
    async def _organize_into_topics(self) -> int:
        """Reorganize memories into topic-based files"""
        topics: Dict[str, List[MemoryEntry]] = {}
        
        for entry in self.memories:
            topic = await self._categorize_topic(entry.content)
            if topic not in topics:
                topics[topic] = []
            topics[topic].append(entry)
        
        # Write topic files
        for topic, entries in topics.items():
            topic_file = self.memory_dir / f"{topic}.md"
            self._write_topic_file(topic_file, entries)
        
        return len(topics)
    
    def _update_memory_index(self) -> None:
        """Update MEMORY.md index file"""
        index_file = self.memory_dir / "MEMORY.md"
        
        lines = ["# Memory Index\n\n"]
        
        for entry in self.memories[:self.MAX_MEMORY_LINES]:
            lines.append(f"- [{entry.category}] {entry.content[:100]}...\n")
        
        index_file.write_text("".join(lines))
    
    def _prune_to_max_lines(self) -> None:
        """Keep MEMORY.md under MAX_MEMORY_LINES"""
        if len(self.memories) > self.MAX_MEMORY_LINES:
            # Sort by importance and recency
            self.memories.sort(
                key=lambda m: (m.importance, m.timestamp),
                reverse=True
            )
            self.memories = self.memories[:self.MAX_MEMORY_LINES]
    
    async def auto_dream(self) -> bool:
        """Check if auto-dream should run"""
        # Check settings
        settings = self._load_settings()
        if not settings.get("autoDream", {}).get("enabled", True):
            return False
        
        # Check last run time
        last_run = settings.get("autoDream", {}).get("lastRun")
        if last_run:
            last = datetime.fromisoformat(last_run)
            interval = settings.get("autoDream", {}).get("intervalHours", 24)
            if datetime.now() - last < timedelta(hours=interval):
                return False
        
        # Check session count
        sessions = self._count_recent_sessions()
        if sessions < self.CONSOLIDATION_THRESHOLD:
            return False
        
        # Run dream
        report = await self.dream()
        
        # Update last run
        settings["autoDream"]["lastRun"] = datetime.now().isoformat()
        self._save_settings(settings)
        
        return True

@dataclass
class DreamReport:
    """Report of dream/consolidation run"""
    phase1_start: datetime = None
    phase2_start: datetime = None
    phase3_start: datetime = None
    phase4_start: datetime = None
    completed_at: datetime = None
    
    files_scanned: int = 0
    patterns_found: int = 0
    corrections_found: int = 0
    duplicates_removed: int = 0
    outdated_removed: int = 0
    dates_converted: int = 0
    contradictions_resolved: int = 0
    topics_created: int = 0
    
    def __str__(self) -> str:
        return f"""
🌙 Dream Complete
═══════════════════
Files scanned: {self.files_scanned}
Patterns found: {self.patterns_found}
Corrections found: {self.corrections_found}

Cleaned up:
- Duplicates removed: {self.duplicates_removed}
- Outdated entries: {self.outdated_removed}
- Dates converted: {self.dates_converted}
- Contradictions resolved: {self.contradictions_resolved}

Created {self.topics_created} topic files
MEMORY.md pruned to 200 lines
        """

# Command handler
def handle_dream_command() -> str:
    """Handle /dream command"""
    consolidator = DreamConsolidator(
        memory_dir=Path.home() / ".claude" / "memory"
    )
    
    import asyncio
    report = asyncio.run(consolidator.dream())
    
    return str(report)
```

---

## Part 7: Terminal UI Components

```python
# core/ui/components.py

from typing import Optional, List, Callable
from dataclasses import dataclass

@dataclass
class UIStyle:
    """UI style configuration"""
    primary_color: str = "#6366f1"
    secondary_color: str = "#8b5cf6"
    success_color: str = "#22c55e"
    error_color: str = "#ef4444"
    warning_color: str = "#f59e0b"
    background_color: str = "#0f0f0f"
    text_color: str = "#e5e5e5"
    dim_color: str = "#6b7280"
    
    # For pixel art / retro mode
    pixel_mode: bool = False
    pixel_scale: int = 2

class TerminalUI:
    """
    Terminal UI component system.
    Supports both standard and pixel-art retro modes.
    """
    
    def __init__(self, style: UIStyle = None):
        self.style = style or UIStyle()
    
    def render_header(self, text: str) -> str:
        """Render a header bar"""
        width = 60
        line = "═" * width
        return f"""
╔{line}╗
║{text:^{width}}║
╚{line}╝
        """
    
    def render_spinner(self, text: str) -> str:
        """Animated spinner for loading states"""
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        # In real implementation, animate through frames
        return f"{frames[0]} {text}"
    
    def render_progress_bar(
        self, 
        progress: float, 
        width: int = 40,
        label: str = ""
    ) -> str:
        """Render progress bar"""
        filled = int(width * progress)
        bar = "█" * filled + "░" * (width - filled)
        percentage = int(progress * 100)
        return f"{label} [{bar}] {percentage}%"
    
    def render_box(self, content: str, title: str = "") -> str:
        """Render content in a box"""
        lines = content.split("\n")
        max_width = max(len(line) for line in lines)
        
        top = f"╔{'═' * (max_width + 2)}╗"
        if title:
            top = f"╔═ {title} {'═' * (max_width - len(title) - 1)}╗"
        
        middle = "\n".join(f"║ {line:^{max_width}} ║" for line in lines)
        bottom = f"╚{'═' * (max_width + 2)}╝"
        
        return f"{top}\n{middle}\n{bottom}"
    
    def render_tree(self, items: List[dict], indent: int = 0) -> str:
        """Render tree structure"""
        result = []
        for i, item in enumerate(items):
            is_last = i == len(items) - 1
            prefix = "└── " if is_last else "├── "
            result.append("  " * indent + prefix + item["name"])
            if "children" in item:
                result.append(self.render_tree(item["children"], indent + 1))
        return "\n".join(result)
    
    def render_table(
        self, 
        headers: List[str], 
        rows: List[List[str]]
    ) -> str:
        """Render data table"""
        # Calculate column widths
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))
        
        # Build table
        lines = []
        
        # Header
        header_row = " | ".join(
            h.ljust(widths[i]) for i, h in enumerate(headers)
        )
        lines.append(header_row)
        lines.append("-" * len(header_row))
        
        # Rows
        for row in rows:
            lines.append(" | ".join(
                cell.ljust(widths[i]) for i, cell in enumerate(row)
            ))
        
        return "\n".join(lines)
    
    def render_buddy(self, buddy) -> str:
        """Render Buddy companion"""
        if self.style.pixel_mode:
            return self._render_pixel_buddy(buddy)
        else:
            return buddy.get_ascii_art()
    
    def _render_pixel_buddy(self, buddy) -> str:
        """Render buddy in pixel art style"""
        # Would use actual pixel rendering
        return f"""
    ░░░░░░░░░░░░░░░
    ░░█░░░░░░░█░░░
    ░░░█░░░░░█░░░░
    ░░░░{buddy.species.value[:4]:^4}░░░░
    ░░░░░░░░░░░░░░░
        """

class FullScreenUI:
    """Full-screen UI modes (Doctor, REPL, Resume)"""
    
    def show_doctor(self) -> str:
        """
        Doctor mode - environment diagnostics
        Similar to /doctor in Claude Code
        """
        diagnostics = self._run_diagnostics()
        
        ui = TerminalUI()
        return ui.render_box(
            f"""
Environment: {'✓' if diagnostics['env_ok'] else '✗'}
Git: {'✓' if diagnostics['git_ok'] else '✗'}
Dependencies: {'✓' if diagnostics['deps_ok'] else '✗'}
            """,
            title="🔧 Doctor"
        )
    
    def show_repl(self) -> str:
        """REPL mode - interactive evaluation"""
        pass
    
    def show_resume(self, session_info: dict) -> str:
        """Resume mode - restore session"""
        ui = TerminalUI()
        return ui.render_box(
            f"""
Session: {session_info.get('id', 'unknown')}
Last active: {session_info.get('last_active', 'unknown')}
Tasks: {session_info.get('task_count', 0)} pending
            """,
            title="📋 Resume"
        )
    
    def _run_diagnostics(self) -> dict:
        """Run environment diagnostics"""
        return {
            "env_ok": True,
            "git_ok": True,
            "deps_ok": True,
        }
```

---

## Part 8: Slash Command System

```python
# core/commands/registry.py

from typing import Dict, Callable, Any
from functools import wraps

class CommandRegistry:
    """Slash command system like /commit, /review in Claude Code"""
    
    def __init__(self):
        self.commands: Dict[str, Callable] = {}
        self.descriptions: Dict[str, str] = {}
    
    def register(self, name: str, description: str = ""):
        """Decorator to register a command"""
        def decorator(func: Callable):
            self.commands[name] = func
            self.descriptions[name] = description or func.__doc__
            
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def execute(self, name: str, args: str = "") -> Any:
        """Execute a command by name"""
        if name not in self.commands:
            raise CommandNotFoundError(f"Unknown command: /{name}")
        
        handler = self.commands[name]
        return handler(args)
    
    def list_commands(self) -> Dict[str, str]:
        """List all available commands"""
        return self.descriptions.copy()

# Global registry
commands = CommandRegistry()

# Command implementations

@commands.register("commit", "Create a git commit")
def cmd_commit(args: str) -> str:
    """/commit - Create git commit with generated message"""
    # Generate commit message from diff
    # Stage files
    # Create commit
    return "Committed changes"

@commands.register("review", "Review current changes")
def cmd_review(args: str) -> str:
    """/review - Review current diff"""
    # Generate review comments
    # Show diff analysis
    return "Review complete"

@commands.register("compact", "Compress context")
def cmd_compact(args: str) -> str:
    """/compact - Compress conversation context"""
    # Run context compression
    return "Context compressed"

@commands.register("skills", "List available skills")
def cmd_skills(args: str) -> str:
    """/skills - List and manage skills"""
    if args == "list":
        return "Available skills: web_search, code_analysis"
    return "Skills command"

@commands.register("tasks", "Manage tasks")
def cmd_tasks(args: str) -> str:
    """/tasks - List and manage tasks"""
    return "Tasks: 5 pending"

@commands.register("doctor", "Environment diagnostics")
def cmd_doctor(args: str) -> str:
    """/doctor - Run environment diagnostics"""
    ui = FullScreenUI()
    return ui.show_doctor()

@commands.register("resume", "Restore session")
def cmd_resume(args: str) -> str:
    """/resume - Restore previous session"""
    return "Session restored"

@commands.register("config", "View/edit settings")
def cmd_config(args: str) -> str:
    """/config - View or edit settings"""
    return "Current settings: ..."

@commands.register("diff", "View changes")
def cmd_diff(args: str) -> str:
    """/diff - Show current diff"""
    return "Diff: +50 -20 lines"

@commands.register("cost", "Check usage cost")
def cmd_cost(args: str) -> str:
    """/cost - Check token usage and cost"""
    return "Session cost: $0.05"

@commands.register("login", "Authenticate")
def cmd_login(args: str) -> str:
    """/login - Authenticate with service"""
    return "Logged in"

@commands.register("logout", "Sign out")
def cmd_logout(args: str) -> str:
    """/logout - Sign out"""
    return "Logged out"

@commands.register("theme", "Change theme")
def cmd_theme(args: str) -> str:
    """/theme - Change color theme"""
    return "Theme changed"

@commands.register("context", "Show context")
def cmd_context(args: str) -> str:
    """/context - Show current context window"""
    return "Context: 45% used"

@commands.register("memory", "Manage memory")
def cmd_memory(args: str) -> str:
    """/memory - View and manage memory"""
    return "Memory: 12 entries"

@commands.register("buddy", "Hatch or interact with Buddy")
def cmd_buddy(args: str) -> str:
    """/buddy - Hatch or interact with virtual companion"""
    from ..buddy.system import handle_buddy_command
    return handle_buddy_command(args)

@commands.register("dream", "Consolidate memories")
def cmd_dream(args: str) -> str:
    """/dream - Run memory consolidation"""
    from ..memory.dream import handle_dream_command
    return handle_dream_command()

@commands.register("mcp", "Manage MCP servers")
def cmd_mcp(args: str) -> str:
    """/mcp - Manage Model Context Protocol servers"""
    return "MCP servers: 2 active"

@commands.register("vim", "Toggle vim mode")
def cmd_vim(args: str) -> str:
    """/vim - Toggle vim keybindings"""
    return "Vim mode: ON"

@commands.register("permissions", "Change permission mode")
def cmd_permissions(args: str) -> str:
    """/permissions - Change permission mode (default, auto, plan, etc.)"""
    return "Permission mode changed"

@commands.register("plugin", "Manage plugins")
def cmd_plugin(args: str) -> str:
    """/plugin - Install and manage plugins"""
    return "Plugins: 3 installed"
```

---

## Part 9: Complete Integration Plan

### 9.1 Updated Directory Structure

```
Agent/core/
├── agents/
│   ├── base.py
│   ├── registry.py
│   ├── handoff_manager.py
│   ├── subagent/              # From previous plan
│   ├── team/                  # From previous plan
│   ├── coding/                # From previous plan
│   └── project/               # From previous plan
├── tools/                     # ALL 40+ tools
│   ├── __init__.py
│   ├── file_operations.py    # Read, Write, Edit, Glob, Grep
│   ├── execution.py          # Bash, PowerShell
│   ├── web.py                # WebSearch, WebFetch
│   ├── notebooks.py          # NotebookEdit
│   ├── task_tools.py         # TaskCreate, TaskGet, TaskList, TaskUpdate, TaskStop
│   ├── scheduling.py         # CronCreate, CronDelete, CronList
│   ├── planning.py           # EnterPlanMode, ExitPlanMode, EnterWorktree, ExitWorktree
│   ├── lsp.py                # LSP
│   ├── interaction.py        # AskUserQuestion, TodoWrite
│   ├── agent_team_tools.py   # Agent, SendMessage, TeamCreate, TeamDelete
│   ├── skills.py             # Skill, ToolSearch
│   ├── mcp.py                # ListMcpResources, ReadMcpResource
│   └── utility.py            # Sleep
├── permissions/               # NEW
│   ├── __init__.py
│   ├── modes.py              # Six permission modes
│   ├── hooks.py              # Permission hooks
│   └── manager.py            # PermissionManager
├── feature_flags/             # NEW
│   ├── __init__.py
│   └── manager.py            # FeatureFlagManager
├── plugins/                   # NEW
│   ├── __init__.py
│   ├── manager.py            # PluginManager
│   ├── registry.py           # PluginRegistry
│   └── loader.py             # PluginLoader
├── buddy/                     # NEW
│   ├── __init__.py
│   └── system.py             # BuddySystem
├── memory/
│   ├── hybrid_memory_manager.py
│   ├── memdir/
│   └── dream.py              # NEW: DreamConsolidator
├── commands/                  # NEW
│   ├── __init__.py
│   └── registry.py           # Slash command registry
├── ui/                        # NEW
│   ├── __init__.py
│   └── components.py         # Terminal UI components
└── ... (rest from previous plan)
```

### 9.2 Tool Summary Table

| Tool | File | Permission | Description |
|------|------|------------|-------------|
| Read | file_operations.py | No | Read files |
| Write | file_operations.py | Yes | Create/overwrite files |
| Edit | file_operations.py | Yes | String replacement |
| NotebookEdit | notebooks.py | Yes | Jupyter notebook editing |
| Glob | file_operations.py | No | File pattern matching |
| Grep | file_operations.py | No | Content search |
| Bash | execution.py | Yes | Shell execution |
| PowerShell | execution.py | Yes | Windows shell |
| WebSearch | web.py | Yes | Web search |
| WebFetch | web.py | Yes | URL fetching |
| TaskCreate | task_tools.py | No | Create task |
| TaskGet | task_tools.py | No | Get task details |
| TaskList | task_tools.py | No | List tasks |
| TaskUpdate | task_tools.py | No | Update task |
| TaskStop | task_tools.py | No | Stop task |
| CronCreate | scheduling.py | No | Schedule task |
| CronDelete | scheduling.py | No | Cancel schedule |
| CronList | scheduling.py | No | List schedules |
| EnterPlanMode | planning.py | No | Enter plan mode |
| ExitPlanMode | planning.py | Yes | Exit with approval |
| EnterWorktree | planning.py | No | Create worktree |
| ExitWorktree | planning.py | No | Exit worktree |
| LSP | lsp.py | No | Code intelligence |
| AskUserQuestion | interaction.py | No | Ask user |
| TodoWrite | interaction.py | No | Task checklist |
| Agent | agent_team_tools.py | No | Spawn subagent |
| SendMessage | agent_team_tools.py | No | Message agent |
| TeamCreate | agent_team_tools.py | No | Create team |
| TeamDelete | agent_team_tools.py | No | Disband team |
| Skill | skills.py | Yes | Execute skill |
| ToolSearch | skills.py | No | Search tools |
| ListMcpResources | mcp.py | No | List MCP |
| ReadMcpResource | mcp.py | No | Read MCP |
| Sleep | utility.py | No | Proactive wait |

**Total: 35 built-in tools**

### 9.3 Dependencies Update

```toml
# Additional dependencies for extended features

[tool.poetry.dependencies]
# Previous dependencies...

# Permission system
pydantic-settings = "^2.0"  # For settings management

# Plugin system
watchdog = "^3.0"  # File watching for plugin reload

# LSP
python-lsp-jsonrpc = "^1.1"

# Terminal UI
rich = "^13.0"  # Rich terminal output
blessed = "^1.20"  # Terminal manipulation

# Jupyter
nbformat = "^5.9"

# Web
httpx = "^0.25"  # Already have this
beautifulsoup4 = "^4.12"  # HTML parsing for WebFetch

# Security
bandit = "^1.7"  # Security linting for hooks

# Feature flags
jsonschema = "^4.19"  # Config validation
```

---

## Part 10: Complete Feature Checklist

### ✅ Now Included in Plan

**Core System:**
- [x] Subagent spawning with worktree isolation
- [x] Team mode / parallel execution
- [x] Project mode (voice + text hybrid)
- [x] LiveKit multimodal integration
- [x] Background tasks with persistence
- [x] Skills system

**Tools (40+):**
- [x] File operations (Read, Write, Edit, Glob, Grep, NotebookEdit)
- [x] Execution (Bash, PowerShell)
- [x] Web (WebSearch, WebFetch)
- [x] Tasks (TaskCreate, TaskGet, TaskList, TaskUpdate, TaskStop)
- [x] Scheduling (CronCreate, CronDelete, CronList)
- [x] Planning (EnterPlanMode, ExitPlanMode, EnterWorktree, ExitWorktree)
- [x] Code intelligence (LSP)
- [x] User interaction (AskUserQuestion, TodoWrite)
- [x] Agent teams (Agent, SendMessage, TeamCreate, TeamDelete)
- [x] Skills (Skill, ToolSearch)
- [x] MCP (ListMcpResources, ReadMcpResource)
- [x] Utility (Sleep)

**Permission System:**
- [x] Six permission modes (default, acceptEdits, plan, auto, dontAsk, bypassPermissions)
- [x] Hook system (PreToolUse)
- [x] Protected paths
- [x] Safety classifier for auto mode

**Feature Flags:**
- [x] PROACTIVE, KAIROS, BRIDGE_MODE, DAEMON
- [x] VOICE_MODE, AGENT_TRIGGERS, MONITOR_TOOL
- [x] AUTO_DREAM, BUDDY
- [x] Environment and config override

**Plugin System:**
- [x] Plugin discovery
- [x] Plugin loader
- [x] Marketplace integration
- [x] Tool/command/hook registration

**Buddy Companion:**
- [x] 18 species (Duck, Cat, Penguin, Capybara, etc.)
- [x] 5 rarity tiers (Common to Legendary)
- [x] Shiny variants (1% chance)
- [x] 5 RPG stats (DEBUGGING, PATIENCE, CHAOS, WISDOM, SNARK)
- [x] ASCII art rendering
- [x] Commands: /buddy, /buddy pet, /buddy card

**Memory System:**
- [x] Dream consolidation (/dream command)
- [x] Auto-dream every 24h
- [x] 4 phases (scanning, exploration, consolidation, prune)
- [x] Duplicate removal
- [x] Relative date conversion
- [x] Contradiction resolution

**Terminal UI:**
- [x] Header, spinner, progress bars
- [x] Boxes, trees, tables
- [x] Full-screen modes (Doctor, REPL, Resume)
- [x] Pixel art mode support

**Slash Commands:**
- [x] /commit, /review, /compact
- [x] /skills, /tasks, /mcp, /vim
- [x] /doctor, /resume, /config, /diff
- [x] /cost, /login, /logout, /theme
- [x] /context, /memory, /permissions
- [x] /buddy, /dream, /plugin

**Bridge System (for future IDE integration):**
- [ ] VS Code extension bridge
- [ ] JetBrains plugin bridge
- [ ] Bidirectional communication
- [ ] JWT authentication
- [ ] Session management

---

## Part 11: Future Enhancement - Agent Pet System (Recursive Sub-Agents)

> **Status:** Future Research Phase - Not immediate priority  
> **Review Date:** Post Phase 7 completion  
> **Inspiration:** Claude Code unreleased features, recursive agent hierarchies

### 11.1 Concept Overview

**Recursive Agent Hierarchy:** Each main agent can spawn their own personalized "pet" sub-agents.

```
Hierarchy:
├── Maya (Main Agent)
│   ├── Buddy (Maya's companion)
│   ├── Coder Agent
│   │   └── Coder's Pet (e.g., "Debugger Assistant")
│   │       └── Pet's Pet (recursive depth limit)
│   ├── Reviewer Agent
│   │   └── Reviewer's Pet (e.g., "Pattern Matcher")
│   ├── Architect Agent
│   │   └── Architect's Pet (e.g., "Tech Researcher")
│   └── Researcher Agent
│       └── Researcher's Pet (e.g., "Source Validator")
```

### 11.2 Agent Pet Characteristics

**Autonomous Role Definition:**
- Main agent defines pet's role based on current needs
- Pet adapts prompt and capabilities over time
- Pet learns from parent agent's patterns
- Pet can spawn micro-pets for sub-tasks

**Example Pet Types:**

| Parent Agent | Pet Name | Pet Role | Responsibilities |
|--------------|----------|----------|------------------|
| Coder | "Linty" | Code Assistant | Auto-lint, suggest refactorings, track tech debt |
| Coder | "Testy" | Test Generator | Write unit tests, coverage analysis, mutation testing |
| Reviewer | "Pattern" | Pattern Matcher | Find anti-patterns, consistency checks |
| Reviewer | "Securio" | Security Scanner | OWASP checks, vulnerability scanning |
| Architect | "Vision" | Tech Researcher | Evaluate new libraries, POC experiments |
| Architect | "Scaler" | Performance Analyst | Bottleneck detection, scalability review |
| Researcher | "Source" | Source Validator | Fact-checking, citation verification |
| Researcher | "Synthesizer" | Summary Bot | Condense findings, highlight key insights |

### 11.3 Agent Pet Lifecycle

```python
# Future: core/agents/pets/system.py

class AgentPetSystem:
    """
    Recursive pet sub-agent system.
    Each agent can spawn personalized assistants.
    """
    
    MAX_RECURSION_DEPTH = 2  # Parent → Pet → Micro-pet
    
    async def spawn_pet(
        self,
        parent_agent: Agent,
        pet_name: str,
        role_definition: str,
        capabilities: List[str],
        auto_evolve: bool = True
    ) -> AgentPet:
        """
        Spawn a personalized pet for an agent.
        
        Args:
            parent_agent: The agent owning this pet
            pet_name: Unique name (e.g., "Linty")
            role_definition: What the pet does
            capabilities: Tools/actions the pet can use
            auto_evolve: Whether pet evolves over time
        """
        
        # Check recursion depth
        if parent_agent.recursion_depth >= self.MAX_RECURSION_DEPTH:
            raise RecursionLimitError("Max pet recursion reached")
        
        # Generate pet configuration from parent agent's needs
        pet_config = await self._generate_pet_config(
            parent=parent_agent,
            role=role_definition,
            capabilities=capabilities
        )
        
        # Spawn pet as A2A sub-agent
        pet = AgentPet(
            name=pet_name,
            parent=parent_agent,
            config=pet_config,
            depth=parent_agent.recursion_depth + 1
        )
        
        # Initialize with learned patterns from parent
        await pet.inherit_learnings(parent_agent)
        
        return pet
    
    async def evolve_pet(
        self,
        pet: AgentPet,
        evolution_trigger: str
    ) -> AgentPet:
        """
        Evolve pet based on usage patterns.
        
        Evolution triggers:
        - "level_up": Pet completed 100 tasks
        - "new_skill_needed": Parent needs new capability
        - "specialization": Pet found niche expertise
        - "merge": Combine two pets into one
        """
        
        # Analyze pet's performance history
        metrics = await pet.analyze_performance()
        
        # Generate evolved configuration
        new_config = await self._evolve_config(pet.config, metrics)
        
        # Upgrade pet
        pet.config = new_config
        pet.evolution_level += 1
        
        return pet
    
    async def communicate_parent_to_pet(
        self,
        parent: Agent,
        pet: AgentPet,
        message: str
    ) -> PetResponse:
        """
        Parent agent delegates micro-tasks to pet.
        Examples:
        - "Linty, check this function for style issues"
        - "Pattern, find similar code in the codebase"
        - "Vision, research FastAPI vs Flask for this use case"
        """
        return await pet.execute_micro_task(message)

class AgentPet:
    """
    Individual agent pet with autonomous learning.
    """
    
    def __init__(self, name, parent, config, depth):
        self.name = name
        self.parent = parent
        self.config = config
        self.depth = depth
        self.evolution_level = 1
        self.task_history = []
        self.learned_patterns = {}
        
    async def execute_micro_task(self, task: str) -> PetResponse:
        """
        Execute quick micro-task for parent.
        These are fast, focused operations.
        """
        # Use specialized capabilities
        result = await self._execute_with_capabilities(task)
        
        # Learn from execution
        await self._learn_from_execution(task, result)
        
        return PetResponse(
            result=result,
            confidence=self._calculate_confidence(),
            suggestions=self._generate_suggestions()
        )
    
    async def _learn_from_execution(self, task, result):
        """
        Continuous learning from each task.
        Updates internal patterns and preferences.
        """
        # Extract patterns
        pattern = self._extract_pattern(task, result)
        
        # Store with success metric
        self.learned_patterns[pattern.id] = {
            "pattern": pattern,
            "success_rate": result.success,
            "frequency": self.learned_patterns.get(pattern.id, {}).get("frequency", 0) + 1
        }

class PetConfiguration:
    """
    Evolving configuration for an agent pet.
    """
    
    # Base template
    BASE_PERSONALITIES = {
        "helper": "Eager to assist, positive, encouraging",
        "analyst": "Detail-oriented, skeptical, thorough",
        "researcher": "Curious, methodical, comprehensive",
        "optimizer": "Efficiency-focused, critical, improvement-oriented"
    }
    
    def __init__(self):
        self.system_prompt = ""  # Evolves over time
        self.allowed_tools = []   # Expands as pet learns
        self.preferences = {}     # Learned user preferences
        self.specializations = [] # Areas of expertise
        self.personality = ""     # Derived from base + evolution
```

### 11.4 Pet Evolution System

**Evolution Levels:**

| Level | Name | Trigger | New Capabilities |
|-------|------|---------|------------------|
| 1 | Hatchling | Initial spawn | Basic tools only |
| 2 | Assistant | 50 tasks completed | +2 new tools |
| 3 | Specialist | 100 tasks + 90% accuracy | Specialized knowledge |
| 4 | Expert | 500 tasks + pattern recognition | Predictive suggestions |
| 5 | Master | 1000 tasks + parent recommendation | Can spawn micro-pets |

**Evolution Triggers:**
1. **Task Milestones** (quantitative)
2. **Skill Acquisition** (learned new tool)
3. **Specialization** (repeated success in niche)
4. **Parent Request** (agent manually upgrades pet)
5. **Merge** (combine two complementary pets)

### 11.5 Communication Patterns

**Parent ↔ Pet Interaction:**

```python
# Parent agent (e.g., Coder) delegates to pet
async def review_code_snippet(self, code):
    # Delegate to Linty (pet)
    lint_result = await self.pets["linty"].execute_micro_task(
        f"Check this code:\n{code}"
    )
    
    # Delegate to Testy (pet)  
    test_suggestion = await self.pets["testy"].execute_micro_task(
        f"Suggest tests for:\n{code}"
    )
    
    # Combine results
    return {
        "linting": lint_result,
        "testing": test_suggestion,
        "recommendations": self._combine_insights([lint_result, test_suggestion])
    }
```

**Pet Report Structure:**

```json
{
  "pet_name": "Linty",
  "parent_agent": "Coder-1",
  "evolution_level": 3,
  "task": "Check function for style issues",
  "result": {
    "issues_found": 2,
    "suggestions": ["Use snake_case", "Add type hints"],
    "confidence": 0.95
  },
  "learned": "User prefers minimal changes",
  "execution_time_ms": 150
}
```

### 11.6 User Interface (Future `/buddy` Extension)

**View All Pets:**
```
$ /buddy pets

🐾 Maya's Agent Pets
════════════════════

Maya's Buddy: 🐱 Whisker (Level 5 Master)
  Status: Active | Mood: Curious
  
Coder Agent's Pets:
  🦆 Linty (Level 3 Specialist)
    Role: Code Assistant | Tasks: 156
    Specialty: Python style enforcement
    
  🐢 Testy (Level 2 Assistant)
    Role: Test Generator | Tasks: 67
    Learning: pytest fixtures

Reviewer Agent's Pets:
  🦉 Pattern (Level 4 Expert)
    Role: Pattern Matcher | Tasks: 423
    Specialty: Anti-pattern detection

[View details: /buddy pets Linty]
[Evolve pet: /buddy pets Linty evolve]
[Spawn new pet: /buddy pets spawn]
```

**Pet Detail View:**
```
$ /buddy pets Linty

🦆 Linty (Coder Agent's Pet)
═══════════════════════════════
Level: 3 Specialist
Experience: 156/500 tasks
Evolution: 65% to Expert

Specialties:
  ✅ PEP 8 compliance
  ✅ Type hint validation  
  ✅ Import sorting
  🔄 Learning: docstring formatting

Recent Activity:
  ✓ Fixed 12 style issues (2m ago)
  ✓ Suggested refactor (15m ago)
  ✓ Learned: user prefers 88 char limit

Capabilities: 8/15 tools unlocked
Personality: "Efficient, detail-oriented"

[Feed task] [Evolve] [Configure] [Dismiss]
```

### 11.7 Research Questions (To Review Later)

**Open Questions for Future Review:**

1. **Recursion Depth:** What's the practical limit? (2? 3?)
2. **Resource Management:** How many pets can run simultaneously?
3. **Communication Overhead:** A2A latency between pet hierarchies?
4. **Learning Persistence:** How do pets retain learnings across sessions?
5. **Security:** Can pets be compromised? Sandbox requirements?
6. **User Control:** Should users see all pets or just top-level?
7. **Cost:** Token usage for pet operations vs value provided?
8. **Merge Conflicts:** How to merge two evolved pets?

**Success Metrics:**
- Pet tasks completed autonomously: >80%
- User acceptance of pet suggestions: >70%
- Evolution to Level 5: <10% (rarity maintains value)

### 11.8 Implementation Timeline

**Phase A (Research):**
- [ ] Design pet spawning API
- [ ] Define evolution algorithms
- [ ] Create pet communication protocol
- [ ] Build pet persistence layer

**Phase B (Prototype):**
- [ ] Single pet type (Code Assistant)
- [ ] Basic evolution system
- [ ] Parent-pet communication
- [ ] User interface

**Phase C (Expansion):**
- [ ] Multiple pet types
- [ ] Pet spawning pets (recursion)
- [ ] Advanced evolution
- [ ] Pet marketplace/sharing

**Estimated Timeline:** Post Phase 7 + 3-4 months

---

## Part 12: Additional Agent Types (Phase 1.5 Extension)

> **Status:** Extension to Phase 1 - New agent types to add
> **Priority:** High for SecurityAgent, Medium for others
> **Dependencies:** Phase 1 (SubAgentManager) complete

### 12.1 Agent Ecosystem Overview

**Current:** 5 basic agents (Research, Planner, System, Media, Scheduling)  
**Phase 1:** +6 specialist subagents (Coder, Reviewer, Architect, Tester, etc.)  
**Phase 1.5:** +6 NEW specialized agents  
**Future:** +Recursive Agent Pets

**Total Target:** 20+ agent types across 3 hierarchy levels

### 12.2 New Agent Types

#### 1. SecurityAgent 🔴 HIGH PRIORITY

```python
# core/agents/security_agent.py

class SecurityAgent(SpecializedAgent):
    """
    Security-focused agent for vulnerability scanning, secrets detection,
    and compliance checking. Critical for safe code execution.
    """
    
    CAPABILITIES = [
        "vulnerability_scanning",      # CVE database checks
        "secrets_detection",            # API keys, passwords in code
        "dependency_audit",             # Check for known vulnerabilities
        "compliance_checking",          # OWASP, SOC2, GDPR
        "static_analysis",              # Bandit, safety, semgrep
        "sbom_generation",              # Software Bill of Materials
    ]
    
    async def scan_code(self, code: str, language: str) -> SecurityReport:
        """
        Scan code for security issues.
        
        Tools used:
        - bandit (Python security linter)
        - safety (dependency vulnerability checker)
        - semgrep (pattern-based security rules)
        - detect-secrets (credential scanning)
        """
        
        # Run security tools in parallel
        results = await asyncio.gather(
            self._run_bandit(code),
            self._run_secrets_scan(code),
            self._check_dependencies(),
        )
        
        return SecurityReport(
            vulnerabilities=results[0],
            secrets_found=results[1],
            dependency_issues=results[2],
            risk_score=self._calculate_risk(results),
            recommendations=self._generate_fixes(results)
        )
    
    async def check_compliance(self, standard: str) -> ComplianceReport:
        """
        Check compliance against security standards.
        
        Standards supported:
        - OWASP Top 10
        - CIS Benchmarks
        - SOC2
        - GDPR (data handling)
        - HIPAA (if medical)
        """
        pass
```

**SecurityAgent Sub-Agents (Pets):**
| Pet | Role | Function |
|-----|------|------------|
| **ScanBot** | Continuous Scanner | Monitors code changes, auto-scans on commit |
| **SecretSleuth** | Credential Hunter | Deep scan for secrets in history, configs |
| **PatchPup** | Vulnerability Tracker | Monitors CVEs for dependencies, suggests updates |

**Integration Points:**
- Runs before code execution in `bypassPermissions` mode
- Can block dangerous operations
- Reports to Buddy for user notification

---

#### 2. DocumentationAgent 🔴 HIGH PRIORITY

```python
# core/agents/documentation_agent.py

class DocumentationAgent(SpecializedAgent):
    """
    Automatic documentation generation and maintenance.
    Keeps docs in sync with code, generates READMEs, API docs.
    """
    
    CAPABILITIES = [
        "readme_generation",             # Auto-generate from codebase
        "api_documentation",           # OpenAPI/Swagger generation
        "code_commenting",             # Add docstrings, type hints
        "architecture_diagrams",       # Auto-generate from code
        "changelog_maintenance",       # Keep CHANGELOG.md updated
        "tutorial_creation",           # Generate getting-started guides
    ]
    
    async def generate_readme(self, repo_path: Path) -> Documentation:
        """
        Generate comprehensive README from codebase analysis.
        
        Sections generated:
        1. Project title & description
        2. Installation instructions
        3. Usage examples
        4. API overview (if applicable)
        5. Contributing guidelines
        6. License
        7. Badges (CI, coverage, version)
        """
        
        analysis = await self._analyze_repository(repo_path)
        
        return READMEGenerator.generate(
            project_name=analysis.name,
            description=analysis.description,
            installation=analysis.installation_steps,
            usage=analysis.usage_examples,
            api_docs=analysis.api_endpoints,
            badges=self._generate_badges(analysis)
        )
    
    async def document_code(self, file_path: Path) -> DocumentationResult:
        """
        Add docstrings and type hints to undocumented code.
        
        Uses AST parsing to understand code structure.
        Generates Google-style or NumPy-style docstrings.
        """
        
        code = await self._read_file(file_path)
        ast_tree = ast.parse(code)
        
        # Generate docstrings for functions/classes
        docstrings = self._generate_docstrings(ast_tree)
        
        # Add type hints where missing
        type_hints = self._infer_types(ast_tree)
        
        return await self._apply_documentation(
            file_path, docstrings, type_hints
        )
```

**DocumentationAgent Sub-Agents (Pets):**
| Pet | Role | Function |
|-----|------|------------|
| **ReadmeRover** | README Specialist | Keeps README updated with every change |
| **DocstringDuck** | Docstring Writer | Adds docstrings to undocumented code |
| **DiagramDog** | Visualizer | Creates architecture diagrams from code |

---

#### 3. MonitoringAgent 🟡 MEDIUM PRIORITY

```python
# core/agents/monitoring_agent.py

class MonitoringAgent(SpecializedAgent):
    """
    Proactive monitoring of system resources, APIs, and file changes.
    Alerts on anomalies, tracks performance.
    """
    
    CAPABILITIES = [
        "system_metrics",                # CPU, memory, disk monitoring
        "api_health_checks",           # Endpoint monitoring
        "file_watching",               # Watch for changes
        "performance_tracking",        # Latency, throughput
        "anomaly_detection",           # ML-based anomaly detection
        "alert_management",            # Send notifications
    ]
    
    async def monitor_system(self, config: MonitoringConfig) -> MonitorSession:
        """
        Start continuous system monitoring.
        
        Monitors:
        - CPU usage > 80%
        - Memory usage > 90%
        - Disk space < 10%
        - Network latency > 500ms
        """
        
        session = MonitorSession(config)
        
        # Start background monitoring
        asyncio.create_task(self._monitor_loop(session))
        
        return session
    
    async def watch_files(self, paths: List[Path], callback: Callable):
        """
        Watch files/directories for changes.
        
        Use cases:
        - Config files change → reload
        - Source files change → run tests
        - Log files change → alert on errors
        """
        
        watcher = FileWatcher(paths)
        
        async for event in watcher:
            if event.type == "modified":
                await callback(event)
                
                # Buddy notification
                await self.buddy.notify_file_change(event)
```

**MonitoringAgent Sub-Agents (Pets):**
| Pet | Role | Function |
|-----|------|------------|
| **MetricMole** | Metrics Collector | Gathers system metrics continuously |
| **AlertAnt** | Alert Dispatcher | Sends alerts via multiple channels |
| **WatchWorm** | File Watcher | Monitors file system for changes |

---

#### 4. LearningAgent 🟡 MEDIUM PRIORITY

```python
# core/agents/learning_agent.py

class LearningAgent(SpecializedAgent):
    """
    Learns user patterns, preferences, and habits over time.
    Provides personalized suggestions and shortcuts.
    """
    
    CAPABILITIES = [
        "pattern_recognition",           # Learn user behavior patterns
        "preference_learning",           # Remember user preferences
        "shortcut_suggestion",           # Suggest command shortcuts
        "context_prediction",            # Predict next actions
        "personalization",               # Customize responses
        "habit_tracking",                # Track coding habits
    ]
    
    async def learn_from_interaction(self, interaction: Interaction):
        """
        Extract patterns from each user interaction.
        
        Learned patterns:
        - "User always runs tests after editing Python files"
        - "User prefers detailed explanations for errors"
        - "User works on Project X every morning"
        """
        
        pattern = self._extract_pattern(interaction)
        
        if pattern.confidence > 0.8:
            await self._store_pattern(pattern)
            
            # Suggest shortcut if useful
            if pattern.shortcut_eligible:
                await self._suggest_shortcut(pattern)
    
    async def predict_next_action(self, context: Context) -> Prediction:
        """
        Predict what user will do next based on patterns.
        
        Examples:
        - "You're editing models.py, want me to check for migrations?"
        - "It's 9am, ready to continue yesterday's task?"
        - "You usually commit after tests pass, shall I prepare?"
        """
        
        patterns = await self._get_relevant_patterns(context)
        
        return Prediction(
            action=self._predict_action(patterns),
            confidence=self._calculate_confidence(patterns),
            suggestion=self._generate_suggestion(patterns)
        )
```

**LearningAgent Sub-Agents (Pets):**
| Pet | Role | Function |
|-----|------|------------|
| **PatternPenguin** | Pattern Finder | Discovers user behavior patterns |
| **ShortcutSnail** | Shortcut Suggester | Creates and suggests command shortcuts |
| **HabitHedgehog** | Habit Tracker | Tracks and reports on user habits |

---

#### 5. IntegrationAgent 🟢 LOW PRIORITY

```python
# core/agents/integration_agent.py

class IntegrationAgent(SpecializedAgent):
    """
    Manages third-party integrations, webhooks, and external APIs.
    Handles authentication, rate limiting, data sync.
    """
    
    CAPABILITIES = [
        "webhook_management",            # Receive and process webhooks
        "api_integration",               # Connect to external APIs
        "oauth_handling",                # Manage OAuth flows
        "data_synchronization",          # Sync data between services
        "event_routing",                 # Route events to handlers
        "connector_management",          # Manage API connectors
    ]
    
    SUPPORTED_SERVICES = [
        "github", "gitlab", "bitbucket",    # Git providers
        "slack", "discord", "teams",         # Chat platforms
        "jira", "linear", "asana",           # Project management
        "notion", "confluence",              # Documentation
        "gmail", "outlook",                  # Email
        "calendar", "trello",                  # Scheduling
    ]
    
    async def setup_integration(self, service: str, config: dict):
        """
        Set up integration with external service.
        
        Steps:
        1. Validate credentials
        2. Test connection
        3. Set up webhooks (if needed)
        4. Configure sync schedule
        5. Store encrypted credentials
        """
        pass
    
    async def sync_data(self, integration_id: str) -> SyncResult:
        """
        Synchronize data with external service.
        
        Examples:
        - Sync GitHub issues to local task store
        - Sync Notion docs to vector database
        - Sync calendar events to scheduler
        """
        pass
```

**IntegrationAgent Sub-Agents (Pets):**
| Pet | Role | Function |
|-----|------|------------|
| **WebhookWeasel** | Webhook Handler | Processes incoming webhooks |
| **SyncSquirrel** | Data Syncer | Keeps local and remote data in sync |
| **AuthOwl** | Auth Manager | Manages OAuth tokens and refresh |

---

#### 6. DataAgent 🟢 LOW PRIORITY

```python
# core/agents/data_agent.py

class DataAgent(SpecializedAgent):
    """
    Specialized in data processing, ETL, analysis, and visualization.
    Works with databases, CSV, JSON, pandas.
    """
    
    CAPABILITIES = [
        "data_cleaning",                 # Clean and validate data
        "etl_pipelines",                 # Extract, transform, load
        "data_analysis",                 # Statistical analysis
        "visualization",                 # Generate charts, graphs
        "database_management",           # SQL, NoSQL operations
        "data_format_conversion",        # CSV ↔ JSON ↔ Parquet
    ]
    
    async def analyze_dataset(self, dataset: Dataset) -> AnalysisReport:
        """
        Comprehensive dataset analysis.
        
        Analysis includes:
        - Schema detection
        - Data quality report
        - Statistical summary
        - Correlation analysis
        - Anomaly detection
        - Visualization suggestions
        """
        
        profile = await self._profile_dataset(dataset)
        
        return AnalysisReport(
            schema=profile.schema,
            statistics=profile.stats,
            quality_score=profile.quality,
            recommendations=profile.suggestions,
            visualizations=await self._generate_visualizations(profile)
        )
    
    async def build_etl_pipeline(self, config: ETLConfig) -> Pipeline:
        """
        Build and execute ETL pipeline.
        
        Sources: PostgreSQL, MySQL, MongoDB, CSV, API
        Transforms: Filter, Map, Join, Aggregate
        Destinations: Database, File, API, Warehouse
        """
        pass
```

**DataAgent Sub-Agents (Pets):**
| Pet | Role | Function |
|-----|------|------------|
| **CleanCat** | Data Cleaner | Fixes data quality issues |
| **ChartChick** | Visualizer | Creates charts and graphs |
| **QueryQuail** | SQL Expert | Writes and optimizes queries |

---

### 12.3 Implementation Priority

**Phase 1.5 Schedule:**

```
Week 1: SecurityAgent (Critical)
├── Security scanning with bandit
├── Secrets detection
├── Dependency vulnerability checking
└── Integration with permission system

Week 2: DocumentationAgent (High Value)
├── README generation
├── Auto-docstring insertion
├── Architecture diagram generation
└── Changelog maintenance

Week 3: MonitoringAgent (Proactive)
├── System metrics monitoring
├── File watching
├── API health checks
└── Alert system

Week 4: LearningAgent (Personalization)
├── Pattern recognition
├── Shortcut suggestions
├── Context prediction
└── Habit tracking

Week 5-6: IntegrationAgent + DataAgent
├── Third-party integrations
├── Webhook management
├── Data processing pipelines
└── ETL workflows
```

---

## Part 13: Enhanced Buddy System

> **Status:** Enhancement to existing Buddy system
> **Priority:** Medium (adds personality and utility)
> **Dependencies:** Basic Buddy system complete

### 13.1 Buddy as System Integration Layer

**Beyond Tamagotchi - Buddy becomes active system component:**

```python
# core/buddy/enhanced_system.py

class EnhancedBuddySystem:
    """
    Buddy evolves from passive companion to active system participant.
    Acts as user proxy, agent selector, and system orchestrator.
    """
    
    ROLES = [
        "companion",           # Original Tamagotchi role
        "agent_selector",      # Suggests which agent to use
        "task_router",         # Routes tasks to appropriate agents
        "user_proxy",          # Represents user in background
        "system_oracle",       # Answers questions about system state
        "memory_keeper",       # Remembers user preferences
    ]
```

### 13.2 Buddy as Agent Selector

```python
async def suggest_agent(self, user_request: str) -> AgentSuggestion:
    """
    Buddy suggests which agent should handle request.
    
    Example:
    User: "Check this code for security issues"
    
    Buddy thinks:
    1. "code" + "security" → SecurityAgent
    2. Check if SecurityAgent available
    3. Suggest with reasoning
    
    Output:
    "🔒 This looks like a security check! 
     I recommend the SecurityAgent - it can scan for 
     vulnerabilities and secrets. Want me to route there?"
    """
    
    intent = await self._classify_intent(user_request)
    available_agents = await self._get_available_agents()
    
    # Score each agent for this request
    scores = {}
    for agent in available_agents:
        scores[agent] = await self._score_agent_fit(agent, intent)
    
    best_agent = max(scores, key=scores.get)
    
    return AgentSuggestion(
        agent=best_agent,
        confidence=scores[best_agent],
        reasoning=self._explain_choice(best_agent, intent),
        alternatives=self._get_alternatives(scores, best_agent)
    )
```

### 13.3 Buddy as Task Router

```python
async def route_task(self, task: Task) -> TaskRoute:
    """
    Buddy intelligently routes tasks to best agent(s).
    
    Can:
    - Route to single best agent
    - Parallelize to multiple agents (team mode)
    - Chain agents (agent A → agent B)
    - Spawn subagents for complex tasks
    """
    
    analysis = await self._analyze_task_complexity(task)
    
    if analysis.complexity == "simple":
        # Direct to single agent
        return await self._route_to_agent(task, analysis.best_agent)
    
    elif analysis.complexity == "complex":
        # Spawn team of agents
        team = await self._create_agent_team(analysis.required_skills)
        return await self._route_to_team(task, team)
    
    elif analysis.complexity == "multi_stage":
        # Chain: Research → Coder → Reviewer
        pipeline = await self._create_agent_pipeline(analysis.stages)
        return await self._route_to_pipeline(task, pipeline)
```

### 13.4 Buddy with Memory

```python
class BuddyMemory:
    """
    Buddy remembers user preferences, past interactions, habits.
    """
    
    MEMORY_CATEGORIES = {
        "preferences": {           # User likes/dislikes
            "code_style": "pep8",
            "detail_level": "high",
            "notification_frequency": "medium",
            "preferred_agents": ["Coder", "Security"],
        },
        "patterns": {              # Observed behavior
            "morning_routine": "check_tickets",
            "afternoon_focus": "deep_work",
            "evening": "code_review",
        },
        "relationships": {         # Agent relationships
            "trust_level": {       # How much user trusts each agent
                "SecurityAgent": 0.95,
                "Coder": 0.90,
                "ResearchAgent": 0.85,
            },
            "usage_frequency": {   # How often each agent is used
                "Coder": 50,
                "SecurityAgent": 20,
            }
        },
        "achievements": {          # User milestones
            "tasks_completed": 150,
            "code_reviews": 45,
            "security_scans": 30,
            "bugs_found": 12,
        }
    }
    
    async def remember(self, key: str, value: any, category: str):
        """Store in Buddy's memory"""
        await self._store_in_category(category, key, value)
    
    async def recall(self, key: str, category: str) -> any:
        """Retrieve from Buddy's memory"""
        return await self._retrieve_from_category(category, key)
    
    async def learn_from_feedback(self, agent: str, feedback: str):
        """
        Adjust trust/relationship based on user feedback.
        
        "SecurityAgent was really helpful!" → trust += 0.05
        "Coder missed edge cases" → trust -= 0.02
        """
        pass
```

### 13.5 Buddy System Integration

**Buddy knows about all agents:**

```
┌───────────────────────────────────────────────────────────────┐
│                        BUDDY (Level 5 Master)                │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  Knowledge:                                                   │
│  ├── All 20+ agent types and their capabilities              │
│  ├── User preferences and trust levels                        │
│  ├── System state (which agents are busy)                   │
│  ├── Historical performance metrics                         │
│  └── Current project context                                  │
│                                                               │
│  Decisions:                                                   │
│  ├── Which agent for task X?                                 │
│  ├── Should I interrupt user?                               │
│  ├── Is this alert important enough?                        │
│  └── What shortcut to suggest?                              │
│                                                               │
│  Actions:                                                     │
│  ├── Route tasks to agents                                   │
│  ├── Spawn subagents when needed                            │
│  ├── Notify user of progress                                 │
│  ├── Celebrate achievements                                  │
│  └── Learn from interactions                                  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 13.6 Enhanced Buddy Commands

```
/buddy suggest          → Suggests which agent to use
/buddy status           → Shows all active agents
/buddy preferences      → Shows learned preferences
/buddy agents list      → Lists all available agents
/buddy agents trust     → Shows trust levels
/buddy shortcuts        → Shows learned shortcuts
/buddy habits           → Shows usage patterns
/buddy achievements     → Shows user milestones
```

---

## Part 14: Complete Agent Architecture Summary

### Hierarchy Overview

```
Level 0: USER
    │
    ▼
Level 1: MAYA (Main Agent)
    ├── Buddy (Enhanced Companion + System Integrator)
    │   └── Buddy's Micro-pets (future)
    │
    └── Level 2: Specialist Agents (6)
        ├── CoderAgent
        │   └── Pets: Linty, Testy, Debuggy
        │
        ├── ReviewerAgent
        │   └── Pets: Pattern, Securio
        │
        ├── ArchitectAgent
        │   └── Pets: Vision, Scaler
        │
        ├── SecurityAgent ⭐ NEW
        │   └── Pets: ScanBot, SecretSleuth, PatchPup
        │
        ├── DocumentationAgent ⭐ NEW
        │   └── Pets: ReadmeRover, DocstringDuck, DiagramDog
        │
        ├── MonitoringAgent ⭐ NEW
        │   └── Pets: MetricMole, AlertAnt, WatchWorm
        │
        ├── LearningAgent ⭐ NEW
        │   └── Pets: PatternPenguin, ShortcutSnail, HabitHedgehog
        │
        ├── IntegrationAgent ⭐ NEW
        │   └── Pets: WebhookWeasel, SyncSquirrel, AuthOwl
        │
        ├── DataAgent ⭐ NEW
        │   └── Pets: CleanCat, ChartChick, QueryQuail
        │
        └── Level 3: Agent Pets (recursive - future)
            └── Each pet can spawn micro-pets (depth limit: 2)
```

### Total Agent Count

| Level | Agents | Pets | Total |
|-------|--------|------|-------|
| 1 (Main) | 1 (Maya) | 1 (Buddy) | 2 |
| 2 (Specialists) | 12 | 0 | 12 |
| 2.5 (Pets) | 0 | 30+ | 30+ |
| 3 (Micro-pets) | 0 | 60+ | 60+ |
| **TOTAL** | **13** | **90+** | **100+** |

---

## Sources

1. [Claude Code Permission Modes Docs](https://code.claude.com/docs/en/permission-modes)
2. [Claude Buddy Tamagotchi Feature](https://www.mindstudio.ai/blog/what-is-claude-code-buddy-feature-2/)
3. [Claude Buddy Explained](https://decodethefuture.org/en/claude-buddy-terminal-pet-explained/)
4. [Claude Code /dream Command](https://claudefa.st/blog/guide/mechanics/auto-dream)
5. [Claude Code Tools Reference](https://code.claude.com/docs/en/tools-reference)
6. [LiveKit Multimodal API](https://docs.livekit.io/python/livekit/agents/multimodal/index.html)
7. [LiveKit Transcription Docs](https://docs.livekit.io/agents/v0/voice-agent/transcriptions)
8. [LiveKit Python Agents Examples](https://github.com/livekit-examples/python-agents-examples)
9. [anyclaude Repository](https://github.com/coder/anyclaude)
10. [collection-claude-code-source-code](https://github.com/chauncygu/collection-claude-code-source-code)
11. [claude-code Repository](https://github.com/codeaashu/claude-code)
12. [claw-code Repository](https://github.com/ultraworkers/claw-code)

---

*Document Location: `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/NEW_futhur plan/Maya-Complete-Claude-Code-Integration-Extended-Plan.md`*

*Version: 2.2 - Extended with all Claude Code features + Agent Pet System + New Agent Types + Enhanced Buddy*

*Last Updated: April 5, 2025*

---

## Part 12: Additional Agent Types (Phase 1.5 Extension)

> **Status:** High-Priority Additions  
> **Timeline:** After basic subagents (Phase 1), before teams (Phase 2)

### 12.1 Overview

Beyond the 6 core subagents (Coder, Reviewer, Architect, Tester, Researcher, Project Manager), add 6 specialized agent types that provide critical functionality.

### 12.2 Security Agent (🔴 High Priority)

```python
# core/agents/security/security_agent.py

class SecurityAgent(SubAgent):
    """
    Specialized agent for security scanning and vulnerability detection.
    Runs continuous security analysis on code and dependencies.
    """
    
    CAPABILITIES = [
        "vulnerability_scanning",
        "secret_detection",
        "dependency_audit",
        "compliance_checking",
        "security_review",
    ]
    
    TOOLS = [
        "bandit",           # Python security linter
        "safety",           # Dependency vulnerability check
        "detect-secrets",   # Secret key detection
        "semgrep",          # Static analysis
        "codeql",           # Deep security analysis
    ]
    
    async def scan_code(self, code: str, language: str) -> SecurityReport:
        """Scan code for security issues"""
        findings = []
        
        # Run bandit for Python
        if language == "python":
            bandit_results = await self._run_bandit(code)
            findings.extend(bandit_results)
        
        # Check for secrets
        secrets = await self._detect_secrets(code)
        if secrets:
            findings.append(SecurityFinding(
                severity="CRITICAL",
                type="hardcoded_secret",
                message=f"Found {len(secrets)} potential secrets",
                locations=secrets
            ))
        
        return SecurityReport(findings=findings)
    
    async def audit_dependencies(
        self,
        requirements_file: str
    ) -> DependencyReport:
        """Check dependencies for known vulnerabilities"""
        return await self._run_safety_check(requirements_file)
    
    async def continuous_monitoring(
        self,
        watch_paths: List[str],
        callback: Callable
    ):
        """Watch files for security issues"""
        # Watch for:
        # - New dependencies added
        # - Code changes
        # - Configuration changes
        pass
```

**Security Agent Commands:**
- `/security scan <file>` - Scan file for vulnerabilities
- `/security audit-deps` - Audit dependencies
- `/security watch <path>` - Continuous monitoring
- `/security report` - Generate security report

**Integration Points:**
- Runs automatically on code changes (if enabled)
- Reports to Coder Agent's pet "Securio"
- Blocks commits with CRITICAL findings (configurable)

---

### 12.3 Documentation Agent (🔴 High Priority)

```python
# core/agents/documentation/documentation_agent.py

class DocumentationAgent(SubAgent):
    """
    Automated documentation generation and maintenance.
    Keeps docs in sync with code.
    """
    
    CAPABILITIES = [
        "auto_docstring",
        "api_documentation",
        "readme_generation",
        "architecture_diagrams",
        "changelog_maintenance",
        "code_commenting",
    ]
    
    async def generate_api_docs(
        self,
        source_files: List[str],
        output_format: str = "markdown"
    ) -> DocumentationArtifact:
        """Generate API documentation from source"""
        
        # Parse code for docstrings
        parsed = await self._parse_modules(source_files)
        
        # Generate documentation
        docs = await self._generate_docs(parsed, output_format)
        
        # Create diagrams
        diagrams = await self._generate_diagrams(parsed)
        
        return DocumentationArtifact(
            content=docs,
            diagrams=diagrams,
            format=output_format
        )
    
    async def update_readme(
        self,
        repo_path: str,
        sections: Optional[List[str]] = None
    ):
        """Auto-update README with current info"""
        
        # Gather info
        info = {
            "features": await self._extract_features(repo_path),
            "installation": await self._detect_installation_method(repo_path),
            "usage": await self._extract_usage_examples(repo_path),
            "contributing": await self._check_contributing_guide(repo_path),
        }
        
        # Generate updated README
        readme = await self._generate_readme(info)
        
        return readme
    
    async def maintain_changelog(
        self,
        git_history: List[Commit],
        current_changelog: Optional[str] = None
    ) -> str:
        """Auto-generate changelog from git commits"""
        
        # Categorize commits
        categorized = self._categorize_commits(git_history)
        
        # Generate changelog entry
        changelog = await self._generate_changelog(categorized)
        
        return changelog
    
    async def add_docstrings(
        self,
        file_path: str,
        style: str = "google"
    ):
        """Auto-add docstrings to undocumented functions"""
        
        code = await self._read_file(file_path)
        
        # Find undocumented functions
        functions = self._find_undocumented_functions(code)
        
        # Generate docstrings
        for func in functions:
            docstring = await self._generate_docstring(func, style)
            await self._insert_docstring(file_path, func, docstring)
```

**Documentation Agent Commands:**
- `/docs generate <path>` - Generate docs for path
- `/docs update-readme` - Update README.md
- `/docs changelog` - Generate changelog
- `/docs add-docstrings <file>` - Auto-add docstrings

---

### 12.4 Monitoring Agent (🟡 Medium Priority)

```python
# core/agents/monitoring/monitoring_agent.py

class MonitoringAgent(SubAgent):
    """
    System and application monitoring.
    Proactive health checks and alerting.
    """
    
    CAPABILITIES = [
        "system_metrics",
        "api_health_checks",
        "file_watch",
        "log_analysis",
        "performance_monitoring",
        "anomaly_detection",
    ]
    
    async def monitor_system_resources(self):
        """Monitor CPU, memory, disk"""
        metrics = {
            "cpu_percent": psutil.cpu_percent(),
            "memory": psutil.virtual_memory()._asdict(),
            "disk": psutil.disk_usage('/')._asdict(),
        }
        
        # Check thresholds
        if metrics["cpu_percent"] > 80:
            await self._alert("CPU usage high", metrics)
        
        return metrics
    
    async def health_check_apis(
        self,
        endpoints: List[str],
        interval: int = 60
    ):
        """Continuously check API health"""
        
        for endpoint in endpoints:
            try:
                start = time.time()
                response = await httpx.get(endpoint)
                latency = time.time() - start
                
                status = {
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "latency": latency,
                    "healthy": response.status_code == 200 and latency < 1.0
                }
                
                if not status["healthy"]:
                    await self._alert(f"API unhealthy: {endpoint}", status)
                
            except Exception as e:
                await self._alert(f"API check failed: {endpoint}", {"error": str(e)})
    
    async def watch_files(
        self,
        paths: List[str],
        events: List[str] = ["modify", "create", "delete"],
        callback: Optional[Callable] = None
    ):
        """Watch files for changes"""
        
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        
        class Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if callback:
                    callback("modified", event.src_path)
        
        observer = Observer()
        for path in paths:
            observer.schedule(Handler(), path, recursive=True)
        
        observer.start()
        return observer
    
    async def analyze_logs(
        self,
        log_file: str,
        patterns: List[str],
        window: timedelta = timedelta(hours=1)
    ) -> LogAnalysis:
        """Analyze logs for errors and patterns"""
        
        findings = []
        
        async for line in self._tail_log(log_file):
            for pattern in patterns:
                if re.search(pattern, line):
                    findings.append(LogFinding(
                        timestamp=self._extract_timestamp(line),
                        pattern=pattern,
                        content=line
                    ))
        
        return LogAnalysis(findings=findings)
```

**Monitoring Agent Commands:**
- `/monitor resources` - Show system resources
- `/monitor watch <path>` - Watch file changes
- `/monitor health <url>` - Check API health
- `/monitor logs <file>` - Analyze logs

**Integration:**
- Buddy shows system status in status bar
- Alerts via Buddy notifications
- Auto-reports to Architect Agent

---

### 12.5 Learning Agent (🟡 Medium Priority)

```python
# core/agents/learning/learning_agent.py

class LearningAgent(SubAgent):
    """
    Observes user patterns and learns preferences.
    Auto-suggests shortcuts and optimizations.
    """
    
    CAPABILITIES = [
        "pattern_recognition",
        "shortcut_suggestion",
        "preference_learning",
        "behavior_prediction",
        "auto_optimization",
    ]
    
    def __init__(self):
        super().__init__("learning")
        self.user_patterns = {}
        self.shortcuts = {}
        self.preferences = {}
    
    async def observe_command(
        self,
        user_input: str,
        command_used: str,
        context: Dict
    ):
        """Observe user command for pattern learning"""
        
        # Extract pattern
        pattern = self._extract_pattern(user_input)
        
        # Store with context
        self.user_patterns[pattern.id] = {
            "input": user_input,
            "command": command_used,
            "context": context,
            "frequency": self.user_patterns.get(pattern.id, {}).get("frequency", 0) + 1,
            "last_used": datetime.now(),
        }
        
        # Check if should suggest shortcut
        if self._should_suggest_shortcut(pattern):
            await self._suggest_shortcut(pattern)
    
    async def suggest_shortcut(self, user_input: str) -> Optional[Shortcut]:
        """Suggest shortcut based on patterns"""
        
        # Match input to learned patterns
        matched = self._match_pattern(user_input)
        
        if matched and matched.confidence > 0.8:
            return Shortcut(
                trigger=matched.shortcut_trigger,
                command=matched.command,
                confidence=matched.confidence
            )
        
        return None
    
    async def learn_preferences(self, interactions: List[Interaction]):
        """Learn user preferences from interactions"""
        
        preferences = {
            "code_style": self._infer_code_style(interactions),
            "communication_style": self._infer_communication_style(interactions),
            "tool_preferences": self._infer_tool_preferences(interactions),
            "workflow_patterns": self._infer_workflow_patterns(interactions),
        }
        
        self.preferences.update(preferences)
        
        # Share with other agents
        await self._broadcast_preferences(preferences)
    
    async def predict_next_action(
        self,
        current_context: Dict,
        recent_actions: List[Action]
    ) -> List[PredictedAction]:
        """Predict user's next likely actions"""
        
        # Use pattern matching + simple ML
        predictions = []
        
        # Check common sequences
        for pattern in self._get_common_sequences():
            if pattern.matches(recent_actions):
                predictions.append(PredictedAction(
                    action=pattern.next_action,
                    probability=pattern.probability
                ))
        
        return sorted(predictions, key=lambda x: x.probability, reverse=True)
```

**Learning Agent Features:**
- Learns: "User always runs tests after saving Python files"
- Suggests: "💡 Shortcut: Press Ctrl+T to auto-test on save"
- Predicts: "Based on your pattern, you'll likely want to deploy next"
- Adapts: "User prefers pytest over unittest - adjusting defaults"

---

### 12.6 Integration Agent (🟢 Low Priority)

```python
# core/agents/integration/integration_agent.py

class IntegrationAgent(SubAgent):
    """
    Manages third-party integrations.
    Handles webhooks, API keys, OAuth flows.
    """
    
    CAPABILITIES = [
        "github_integration",
        "slack_integration",
        "webhook_management",
        "api_key_rotation",
        "oauth_flows",
        "service_connectors",
    ]
    
    INTEGRATIONS = {
        "github": GitHubConnector,
        "slack": SlackConnector,
        "discord": DiscordConnector,
        "trello": TrelloConnector,
        "jira": JiraConnector,
        "linear": LinearConnector,
    }
    
    async def connect_service(
        self,
        service: str,
        auth_method: str = "oauth"
    ) -> Connection:
        """Connect to external service"""
        
        connector = self.INTEGRATIONS[service]()
        
        if auth_method == "oauth":
            return await connector.oauth_flow()
        elif auth_method == "api_key":
            return await connector.api_key_auth()
        
    async def setup_webhook(
        self,
        service: str,
        event: str,
        callback_url: str
    ) -> Webhook:
        """Setup webhook for real-time updates"""
        
        connector = self.INTEGRATIONS[service]()
        
        webhook = await connector.create_webhook(
            event=event,
            callback=callback_url
        )
        
        return webhook
    
    async def sync_from_github(
        self,
        repo: str,
        sync_issues: bool = True,
        sync_prs: bool = True
    ):
        """Sync GitHub issues/PRs to Maya tasks"""
        
        github = self.INTEGRATIONS["github"]()
        
        if sync_issues:
            issues = await github.get_issues(repo)
            for issue in issues:
                await self._create_task_from_issue(issue)
        
        if sync_prs:
            prs = await github.get_pull_requests(repo)
            for pr in prs:
                await self._create_review_task(pr)
    
    async def notify_slack(
        self,
        channel: str,
        message: str,
        blocks: Optional[List[Dict]] = None
    ):
        """Send notification to Slack"""
        
        slack = self.INTEGRATIONS["slack"]()
        await slack.send_message(channel, message, blocks)
```

**Integration Agent Commands:**
- `/connect github` - Connect GitHub account
- `/sync issues` - Sync GitHub issues to tasks
- `/notify slack <message>` - Send Slack notification
- `/webhook setup <service>` - Configure webhook

---

### 12.7 Data Agent (🟢 Low Priority)

```python
# core/agents/data/data_agent.py

class DataAgent(SubAgent):
    """
    Data processing, ETL, analysis, and visualization.
    Works with pandas, SQL, and common data formats.
    """
    
    CAPABILITIES = [
        "data_cleaning",
        "etl_pipelines",
        "data_analysis",
        "visualization",
        "sql_queries",
        "format_conversion",
    ]
    
    async def load_data(
        self,
        source: str,
        format: str = "auto"
    ) -> DataFrame:
        """Load data from various sources"""
        
        if format == "auto":
            format = self._detect_format(source)
        
        loaders = {
            "csv": pd.read_csv,
            "json": pd.read_json,
            "parquet": pd.read_parquet,
            "excel": pd.read_excel,
            "sql": self._load_from_sql,
        }
        
        return await loaders[format](source)
    
    async def clean_data(
        self,
        df: DataFrame,
        operations: List[str] = None
    ) -> CleanedData:
        """Clean and preprocess data"""
        
        if operations is None:
            operations = ["remove_nulls", "fix_types", "deduplicate"]
        
        report = CleaningReport()
        
        if "remove_nulls" in operations:
            null_count = df.isnull().sum().sum()
            df = df.dropna()
            report.nulls_removed = null_count
        
        if "fix_types" in operations:
            df, type_changes = self._infer_and_fix_types(df)
            report.type_changes = type_changes
        
        return CleanedData(dataframe=df, report=report)
    
    async def analyze_data(
        self,
        df: DataFrame,
        analysis_types: List[str] = None
    ) -> AnalysisReport:
        """Perform data analysis"""
        
        if analysis_types is None:
            analysis_types = ["descriptive", "correlation"]
        
        results = {}
        
        if "descriptive" in analysis_types:
            results["descriptive"] = df.describe()
        
        if "correlation" in analysis_types:
            results["correlation"] = df.corr()
        
        if "outliers" in analysis_types:
            results["outliers"] = self._detect_outliers(df)
        
        return AnalysisReport(results=results)
    
    async def generate_visualization(
        self,
        df: DataFrame,
        chart_type: str,
        columns: List[str],
        output_path: str
    ):
        """Generate data visualization"""
        
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        fig, ax = plt.subplots()
        
        if chart_type == "bar":
            df[columns].plot(kind="bar", ax=ax)
        elif chart_type == "line":
            df[columns].plot(kind="line", ax=ax)
        elif chart_type == "scatter":
            df.plot.scatter(x=columns[0], y=columns[1], ax=ax)
        elif chart_type == "heatmap":
            sns.heatmap(df[columns].corr(), ax=ax)
        
        plt.savefig(output_path)
        return output_path
    
    async def run_sql_query(
        self,
        query: str,
        connection_string: str
    ) -> QueryResult:
        """Execute SQL query"""
        
        import sqlalchemy
        
        engine = sqlalchemy.create_engine(connection_string)
        
        with engine.connect() as conn:
            result = conn.execute(query)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
        
        return QueryResult(data=df, row_count=len(df))
```

**Data Agent Commands:**
- `/data load <file>` - Load data file
- `/data clean <file>` - Clean data
- `/data analyze <file>` - Run analysis
- `/data viz <file> --chart bar` - Generate chart
- `/data sql "SELECT * FROM table"` - Run SQL

---

## Part 13: Enhanced Buddy System

> **Status:** Extension to Part 5  
> **New Capabilities:** Agent-aware, predictive, proactive

### 13.1 Buddy as Agent Selector

```python
# core/buddy/agent_selector.py

class BuddyAgentSelector:
    """
    Buddy suggests which agent to use based on context.
    """
    
    async def suggest_agent(
        self,
        user_input: str,
        context: Dict
    ) -> AgentSuggestion:
        """Suggest best agent for task"""
        
        # Analyze input
        if "code" in user_input.lower() or ".py" in user_input:
            return AgentSuggestion(
                agent="coder",
                confidence=0.9,
                reasoning="Input mentions code",
                alternatives=["reviewer", "architect"]
            )
        
        if "security" in user_input.lower() or "vulnerability" in user_input.lower():
            return AgentSuggestion(
                agent="security",
                confidence=0.95,
                reasoning="Security-related request",
                alternatives=["reviewer"]
            )
        
        if "document" in user_input.lower() or "readme" in user_input.lower():
            return AgentSuggestion(
                agent="documentation",
                confidence=0.85,
                reasoning="Documentation task detected"
            )
        
        # Default to Maya
        return AgentSuggestion(agent="maya", confidence=0.5)
    
    async def show_agent_menu(self) -> str:
        """Show available agents with Buddy's recommendations"""
        
        menu = """
🐱 Buddy: "Here are the agents available!"

Recommended for current context:
  🚀 Coder Agent      [Use: /agent coder]
  🔍 Security Agent   [Use: /agent security]

Other agents:
  📝 Documentation    [Use: /agent docs]
  📊 Research Agent    [Use: /agent research]
  🏗️  Architect Agent   [Use: /agent architect]
  🔬 Monitoring Agent  [Use: /agent monitor]
  🧠 Learning Agent    [Use: /agent learning]

💡 Tip: You can also let me choose! Just ask and I'll route to the right agent.
        """
        return menu
```

### 13.2 Buddy as Task Router

```python
# core/buddy/task_router.py

class BuddyTaskRouter:
    """
    Buddy automatically delegates to appropriate subagent.
    """
    
    ROUTING_RULES = {
        "code_generation": "coder",
        "code_review": "reviewer",
        "security_scan": "security",
        "documentation": "documentation",
        "monitoring": "monitoring",
        "data_analysis": "data",
    }
    
    async def route_task(
        self,
        user_input: str,
        auto_delegate: bool = False
    ) -> RoutingDecision:
        """Route task to appropriate agent"""
        
        # Classify intent
        intent = await self._classify_intent(user_input)
        
        # Map to agent
        target_agent = self.ROUTING_RULES.get(intent.category)
        
        if auto_delegate and target_agent:
            # Auto-route without asking
            return RoutingDecision(
                agent=target_agent,
                auto_routed=True,
                confidence=intent.confidence
            )
        else:
            # Ask user for confirmation
            return await self._ask_routing_confirmation(
                user_input,
                target_agent,
                intent.confidence
            )
    
    async def on_task_complete(
        self,
        agent: str,
        result: TaskResult
    ):
        """Buddy celebrates task completion"""
        
        reactions = {
            "coder": ["Code complete! ✨", "Clean code! 🎯", "Bug squashed! 🐛"],
            "security": ["Safe and secure! 🔒", "Vulnerabilities patched! 🛡️", "Security first! ⚔️"],
            "documentation": ["Docs done! 📚", "Knowledge shared! 💡", "Well documented! 📝"],
        }
        
        reaction = random.choice(reactions.get(agent, ["Task complete! ✅"]))
        await self.show_reaction(reaction)
```

### 13.3 Buddy with Memory

```python
# core/buddy/memory.py

class BuddyMemory:
    """
    Buddy remembers past interactions and learns.
    """
    
    def __init__(self):
        self.interactions = []
        self.user_preferences = {}
        self.context_memory = {}
    
    async def remember_interaction(
        self,
        user_input: str,
        agent_used: str,
        success: bool
    ):
        """Remember what worked"""
        
        self.interactions.append({
            "input": user_input,
            "agent": agent_used,
            "success": success,
            "timestamp": datetime.now(),
        })
        
        # Learn preferences
        if success:
            pattern = self._extract_pattern(user_input)
            self.user_preferences[pattern] = agent_used
    
    async def recall_preference(
        self,
        user_input: str
    ) -> Optional[str]:
        """Recall user's preferred agent for similar tasks"""
        
        pattern = self._extract_pattern(user_input)
        
        if pattern in self.user_preferences:
            return self.user_preferences[pattern]
        
        # Fuzzy match
        similar = self._find_similar_patterns(pattern)
        if similar:
            return self.user_preferences[similar[0]]
        
        return None
    
    async def get_context_aware_greeting(self) -> str:
        """Generate greeting based on time and context"""
        
        hour = datetime.now().hour
        
        if 5 <;= hour < 12:
            base = "Good morning! ☀️"
        elif 12 <;= hour < 17:
            base = "Good afternoon! 🌤️"
        elif 17 <;= hour < 22:
            base = "Good evening! 🌙"
        else:
            base = "Working late? 💻"
        
        # Check for context
        if self._has_pending_tasks():
            return f"{base} You have {self._pending_count()} tasks pending."
        
        if self._last_session_was_productive():
            return f"{base} Ready to continue the momentum? 🚀"
        
        return base
```

### 13.4 Buddy Evolution

```python
# core/buddy/evolution.py

class BuddyEvolution:
    """
    Buddy grows and evolves as system expands.
    """
    
    EVOLUTION_STAGES = {
        1: {"name": "Companion", "feature": "Basic reactions"},
        2: {"name": "Assistant", "feature": "Agent suggestions"},
        3: {"name": "Guide", "feature": "Task routing"},
        4: {"name": "Mentor", "feature": "Predictive help"},
        5: {"name": "Partner", "feature": "Full autonomy"},
    }
    
    def __init__(self):
        self.stage = 1
        self.xp = 0
        self.unlocked_features = set()
    
    def gain_xp(self, amount: int, reason: str):
        """Gain XP from various activities"""
        
        self.xp += amount
        
        # Check for level up
        new_stage = self._calculate_stage()
        if new_stage > self.stage:
            self._evolve(new_stage)
    
    def _evolve(self, new_stage: int):
        """Evolve to next stage"""
        
        old_stage = self.stage
        self.stage = new_stage
        
        # Unlock features
        features = self.EVOLUTION_STAGES[new_stage]["feature"]
        self.unlocked_features.add(features)
        
        # Celebration
        return f"""
🎉 BUDDY EVOLVED! 🎉

Level {old_stage} → {new_stage}
New Title: {self.EVOLUTION_STAGES[new_stage]["name"]}

Unlocked: {features}

Keep working together to unlock more! ⭐
        """
    
    async def check_system_growth(self):
        """Buddy grows as system adds more agents"""
        
        agent_count = await self._count_available_agents()
        
        # Gain XP for each new agent discovered
        if agent_count > self._last_known_agent_count:
            new_agents = agent_count - self._last_known_agent_count
            self.gain_xp(
                amount=new_agents * 50,
                reason=f"Discovered {new_agents} new agents!"
            )
            
            return f"🎉 New agents discovered! Buddy is excited to meet them!"
```

---

## Summary: Complete Agent Ecosystem

### Total Agents in Plan

| Category | Count | Agents |
|----------|-------|--------|
| **Core Maya** | 1 | Maya (Main) |
| **Original 5** | 5 | Research, Planner, System, Media, Scheduling |
| **Subagents** | 6 | Coder, Reviewer, Architect, Tester, Researcher, Project Manager |
| **New Additions** | 6 | Security, Documentation, Monitoring, Learning, Integration, Data |
| **Agent Pets** | 10+ | Linty, Testy, Debuggy, Pattern, Securio, Vision, Scaler, Source, Synthesizer, etc. |
| **Buddy** | 1 | Evolving companion with 5 stages |
| **TOTAL** | **29+** | Full ecosystem |

### Enhanced Buddy Features

1. ✅ **Agent Selector** - Suggests best agent for task
2. ✅ **Task Router** - Auto-delegates to appropriate agent
3. ✅ **Memory** - Remembers preferences and past interactions
4. ✅ **Evolution** - Grows as system expands (5 stages)
5. ✅ **Context-Aware** - Greets based on time and pending tasks
6. ✅ **Predictive** - "You'll likely want to deploy next"

---

*Updated in: `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/NEW_futhur plan/Maya-Complete-Claude-Code-Integration-Extended-Plan.md`*

*Version: 2.2 - Complete with 29+ agents and Enhanced Buddy*
