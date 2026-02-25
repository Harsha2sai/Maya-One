import os
import json
import logging
import sys
from typing import List
from mcp_client.server import MCPServer, MCPServerStdio, MCPServerSse

logger = logging.getLogger(__name__)

class PluginManager:
    @staticmethod
    def load_plugins(base_dir: str = None) -> List[MCPServer]:
        """
        Scans the plugins directory and initializes MCP server instances for each plugin found.
        Supports both .json configurations and .py FastMCP-based plugins.
        """
        servers = []

        if base_dir is None:
            # Default to the directory where this file is located
            base_dir = os.path.dirname(os.path.abspath(__file__))

        logger.info(f"🔍 Scanning for plugins in: {base_dir}")

        for root, dirs, files in os.walk(base_dir):
            for file in files:
                # Skip manager and init files
                if file in ["manager.py", "__init__.py"]:
                    continue

                filepath = os.path.join(root, file)

                # Option 1: JSON Configuration
                if file.endswith(".json"):
                    try:
                        with open(filepath, 'r') as f:
                            config = json.load(f)

                        name = config.get("name", file)
                        if config.get("type") == "sse":
                            servers.append(MCPServerSse(
                                params=config,
                                name=name,
                                cache_tools_list=True
                            ))
                        else:
                            # Ensure command is present
                            if "command" in config:
                                servers.append(MCPServerStdio(
                                    params=config,
                                    name=name,
                                    cache_tools_list=True
                                ))
                        logger.info(f"✅ Loaded JSON plugin: {name}")
                    except Exception as e:
                        logger.error(f"❌ Failed to load JSON plugin {file}: {e}")

                # Option 2: Python FastMCP Plugin
                elif file.endswith(".py"):
                    try:
                        name = f"Python Plugin ({file})"
                        # We run the python file as a stdio server
                        servers.append(MCPServerStdio(
                            params={
                                "command": sys.executable,
                                "args": [filepath],
                                "env": os.environ.copy()
                            },
                            name=name,
                            cache_tools_list=True
                        ))
                        logger.info(f"✅ Loaded Python plugin: {file}")
                    except Exception as e:
                        logger.error(f"❌ Failed to prepare Python plugin {file}: {e}")

        return servers
