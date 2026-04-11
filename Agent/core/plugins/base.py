from __future__ import annotations

from abc import ABC, abstractmethod

from core.commands.registry import CommandRegistry


class MayaPlugin(ABC):
    name: str
    version: str
    description: str

    @abstractmethod
    def register(self, registry: CommandRegistry) -> None:
        """Register this plugin's slash commands."""
        raise NotImplementedError

