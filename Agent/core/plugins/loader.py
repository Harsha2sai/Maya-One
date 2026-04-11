from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Dict, List

from core.commands.registry import CommandRegistry
from core.plugins.base import MayaPlugin

logger = logging.getLogger(__name__)


class PluginLoader:
    def __init__(self, plugin_dir: str = "plugins"):
        self._dir = Path(plugin_dir)
        self._loaded: Dict[str, MayaPlugin] = {}

    def discover(self) -> List[str]:
        if not self._dir.exists():
            return []
        return sorted(
            [
                p.stem
                for p in self._dir.glob("*.py")
                if not p.stem.startswith("_")
            ]
        )

    def load(self, name: str, registry: CommandRegistry) -> bool:
        path = self._dir / f"{name}.py"
        if not path.exists():
            return False

        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                return False
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            plugin = getattr(mod, "plugin", None)
            if plugin is None or not hasattr(plugin, "register"):
                return False
            plugin.register(registry)
            self._loaded[name] = plugin
            return True
        except Exception as exc:
            logger.warning("plugin_load_failed name=%s error=%s", name, exc)
            return False

    def load_all(self, registry: CommandRegistry) -> List[str]:
        loaded = []
        for name in self.discover():
            if self.load(name, registry):
                loaded.append(name)
        return loaded

    def loaded(self) -> Dict[str, MayaPlugin]:
        return dict(self._loaded)

