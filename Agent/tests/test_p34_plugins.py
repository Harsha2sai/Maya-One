from __future__ import annotations

from pathlib import Path

from core.commands.registry import CommandRegistry
from core.plugins.loader import PluginLoader


def test_plugin_loader_discover_empty_when_dir_missing(tmp_path):
    loader = PluginLoader(plugin_dir=str(tmp_path / "missing"))
    assert loader.discover() == []


def test_plugin_loader_load_all_empty_dir_returns_empty(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    loader = PluginLoader(plugin_dir=str(plugin_dir))
    loaded = loader.load_all(CommandRegistry())
    assert loaded == []


def test_plugin_loader_valid_plugin_registers_commands(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "demo.py"
    plugin_file.write_text(
        "\n".join(
            [
                "from core.plugins.base import MayaPlugin",
                "from core.commands.registry import SlashCommand",
                "class DemoPlugin(MayaPlugin):",
                "    name = 'demo'",
                "    version = '0.1.0'",
                "    description = 'demo plugin'",
                "    def register(self, registry):",
                "        async def _handler(args, context):",
                "            return 'demo:' + str(args)",
                "        registry.register(SlashCommand('demo', 'Demo command', '/demo', _handler))",
                "plugin = DemoPlugin()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    registry = CommandRegistry()
    loader = PluginLoader(plugin_dir=str(plugin_dir))
    assert loader.load("demo", registry) is True
    assert registry.get("demo") is not None


def test_plugin_loader_missing_plugin_export_fails_gracefully(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "broken.py"
    plugin_file.write_text("x = 1\n", encoding="utf-8")

    registry = CommandRegistry()
    loader = PluginLoader(plugin_dir=str(plugin_dir))
    assert loader.load("broken", registry) is False


def test_plugin_loader_loaded_plugin_appears_in_loaded_map(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "okplugin.py"
    plugin_file.write_text(
        "\n".join(
            [
                "from core.plugins.base import MayaPlugin",
                "class OkPlugin(MayaPlugin):",
                "    name = 'okplugin'",
                "    version = '0.1.0'",
                "    description = 'ok plugin'",
                "    def register(self, registry):",
                "        return None",
                "plugin = OkPlugin()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    registry = CommandRegistry()
    loader = PluginLoader(plugin_dir=str(plugin_dir))
    assert loader.load("okplugin", registry) is True
    assert "okplugin" in loader.loaded()

