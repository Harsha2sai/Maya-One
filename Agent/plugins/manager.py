import os
import json
import logging
import sys
import time
import importlib.util
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from mcp_client.server import MCPServer, MCPServerStdio, MCPServerSse

logger = logging.getLogger(__name__)

@dataclass
class PluginMetadata:
    name: str
    category: str = "general"
    mode: str = "mcp" # "mcp", "wrapped-mcp", "local-native"
    risk_level: str = "low" # "low", "medium", "high"
    confirmation_required: List[str] = field(default_factory=list)
    rate_limit: int = 0 # 0 means no limit
    destructive: bool = False
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    type: str = "stdio" # "stdio" or "sse"
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)

class Plugin:
    def __init__(self, path: str):
        self.path = path
        self.metadata: Optional[PluginMetadata] = None
        self.tools: List[Dict[str, Any]] = []
        self.rules: Dict[str, Any] = {}
        self.server: Optional[MCPServer] = None
        self.adapter: Any = None
        self._load()

    def _load(self):
        # 1. Load plugin.json (Metadata)
        meta_path = os.path.join(self.path, "plugin.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r') as f:
                    data = json.load(f)
                    self.metadata = PluginMetadata(**data)
            except Exception as e:
                logger.error(f"Error loading metadata from {meta_path}: {e}")

        # 2. Load tools.json (Tool definitions)
        tools_path = os.path.join(self.path, "tools.json")
        if os.path.exists(tools_path):
            try:
                with open(tools_path, 'r') as f:
                    data = json.load(f)
                    self.tools = data.get("tools", [])
            except Exception as e:
                logger.error(f"Error loading tools from {tools_path}: {e}")

        # 3. Load rules.json (Safety)
        rules_path = os.path.join(self.path, "rules.json")
        if os.path.exists(rules_path):
            try:
                with open(rules_path, 'r') as f:
                    self.rules = json.load(f)
                    if self.metadata:
                        if not self.metadata.confirmation_required:
                            self.metadata.confirmation_required = self.rules.get("confirmation_required", [])
                        if not self.metadata.rate_limit:
                            self.metadata.rate_limit = self.rules.get("rate_limit", 0)
            except Exception as e:
                logger.error(f"Error loading rules from {rules_path}: {e}")

        # 4. Initialize MCP Server if needed
        # We look for server config in plugin.json or a default mcp_config.json
        if self.metadata and (self.metadata.mode in ["mcp", "wrapped-mcp"] or (self.metadata.mode == "local-native" and self.metadata.command)):
            # Re-read plugin.json for server params
            with open(meta_path, 'r') as f:
                config = json.load(f)

            server_name = config.get("name", os.path.basename(self.path))
            if config.get("type") == "sse":
                self.server = MCPServerSse(params=config, name=server_name)
            elif "command" in config:
                # Resolve paths in args relative to plugin path
                args = config.get("args", [])
                resolved_args = []
                for arg in args:
                    if "{{PLUGIN_PATH}}" in arg:
                        arg = arg.replace("{{PLUGIN_PATH}}", self.path)
                    resolved_args.append(arg)

                config["args"] = resolved_args
                self.server = MCPServerStdio(params=config, name=server_name)

        # 5. Load adapter.py if exists
        adapter_path = os.path.join(self.path, "adapter.py")
        if os.path.exists(adapter_path):
            try:
                module_name = f"plugin_adapter_{self.metadata.name if self.metadata else os.path.basename(self.path)}"
                spec = importlib.util.spec_from_file_location(module_name, adapter_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Look for a class named Adapter or SpotifyAdapter etc.
                adapter_class = getattr(module, "Adapter", None)
                if not adapter_class:
                    # Search for any class ending in 'Adapter'
                    for attr_name in dir(module):
                        if attr_name.endswith("Adapter"):
                            adapter_class = getattr(module, attr_name)
                            break

                if adapter_class:
                    self.adapter = adapter_class(server=self.server)
                    logger.info(f"✅ Loaded adapter for {self.metadata.name if self.metadata else self.path}")
            except Exception as e:
                logger.error(f"❌ Failed to load adapter from {adapter_path}: {e}")

    async def invoke(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Invoke a tool through the adapter if available, otherwise direct to server."""
        if self.adapter:
            # Check if adapter has a method for this tool
            # Most adapters use more pythonic names than MCP tool names
            method_name = tool_name.replace("send_whatsapp_message", "send_message").replace("play_music", "play_music")
            # For simplicity, if tool_name is in adapter, call it
            method = getattr(self.adapter, tool_name, None) or getattr(self.adapter, method_name, None)
            if method and callable(method):
                logger.info(f"🔌 Using adapter for tool: {tool_name}")
                return await method(**arguments)

        if self.server:
            # Direct MCP call
            result = await self.server.call_tool(tool_name, arguments)
            # Standard MCP result extraction (assuming result is a CallToolResult or dict)
            if hasattr(result, 'content') and isinstance(result.content, list):
                return "\n".join([c.text if hasattr(c, 'text') else str(c) for c in result.content])
            elif isinstance(result, dict) and 'content' in result:
                return str(result['content'])
            return str(result)

        return f"Error: No implementation for tool {tool_name} in plugin {self.metadata.name if self.metadata else 'unknown'}"

class SafetyGuard:
    def __init__(self):
        self.tool_call_history: Dict[str, List[float]] = {}

    def check_rate_limit(self, plugin: 'Plugin') -> bool:
        if not plugin.metadata or plugin.metadata.rate_limit <= 0:
            return True

        now = time.time()
        minute_ago = now - 60

        # Track history for this plugin
        plugin_name = plugin.metadata.name
        if plugin_name not in self.tool_call_history:
            self.tool_call_history[plugin_name] = []

        # Clean old calls
        self.tool_call_history[plugin_name] = [t for t in self.tool_call_history[plugin_name] if t > minute_ago]

        if len(self.tool_call_history[plugin_name]) >= plugin.metadata.rate_limit:
            return False

        self.tool_call_history[plugin_name].append(now)
        return True

class PluginManager:
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.base_dir = base_dir
        self.plugins: Dict[str, Plugin] = {}
        self.safety_guard = SafetyGuard()

    def load_all_plugins(self) -> List[MCPServer]:
        """Scans for and loads all plugins in the directory structure."""
        servers = []
        logger.info(f"🔍 Scanning for plugins in: {self.base_dir}")

        # Scan for directories containing plugin.json
        for root, dirs, files in os.walk(self.base_dir):
            if "plugin.json" in files:
                try:
                    plugin = Plugin(root)
                    if plugin.metadata:
                        self.plugins[plugin.metadata.name] = plugin
                        if plugin.server:
                            servers.append(plugin.server)
                            logger.info(f"✅ Loaded plugin: {plugin.metadata.name}")
                    else:
                        logger.warning(f"⚠️ Plugin at {root} has no metadata")
                except Exception as e:
                    logger.error(f"❌ Failed to load plugin at {root}: {e}")

                # Prevent walking into subdirectories of a plugin (like mcp_server/)
                # dirs[:] = []
                # Actually, let's just skip walking further if we found a plugin.json here.
                # But sometimes we might have plugins inside categories.
                # If we found a plugin here, we shouldn't walk deeper into its mcp_server etc.
                dirs[:] = [d for d in dirs if d not in ["mcp_server", "venv", ".git", "__pycache__"]]

        return servers

    def get_plugin(self, name: str) -> Optional[Plugin]:
        return self.plugins.get(name)

    def check_confirmation_required(self, tool_name: str) -> bool:
        """Check if a tool requires user confirmation based on rules."""
        for plugin in self.plugins.values():
            if plugin.metadata and tool_name in plugin.metadata.confirmation_required:
                return True
        return False

    def check_safety(self, tool_name: str) -> (bool, str):
        """Perform full safety check for a tool (confirmation + rate limiting)."""
        target_plugin = None
        # We need to find which plugin this tool belongs to
        # For simplicity, we search all plugins' tools metadata if we have it
        for plugin in self.plugins.values():
            if any(t.get("name") == tool_name for t in plugin.tools):
                target_plugin = plugin
                break

        if not target_plugin:
            # Fallback check for confirmation by name only
            if self.check_confirmation_required(tool_name):
                return True, "Confirmation Required"
            return True, "Safe"

        # 1. Check Rate Limit
        if not self.safety_guard.check_rate_limit(target_plugin):
            return False, f"Rate limit exceeded for plugin {target_plugin.metadata.name}"

        # 2. Check Confirmation
        if tool_name in target_plugin.metadata.confirmation_required:
            return True, "Confirmation Required"

        return True, "Safe"
