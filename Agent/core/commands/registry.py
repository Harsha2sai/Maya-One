from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional


@dataclass
class SlashCommand:
    name: str
    description: str
    usage: str
    handler: Callable[..., Awaitable[str]]
    requires_mode: Optional[str] = None


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: Dict[str, SlashCommand] = {}

    def register(self, cmd: SlashCommand) -> None:
        self._commands[cmd.name.lower()] = cmd

    def get(self, name: str) -> Optional[SlashCommand]:
        return self._commands.get(str(name or "").strip().lower())

    def all(self) -> Dict[str, SlashCommand]:
        return dict(self._commands)

    async def dispatch(self, raw: str, context: dict) -> Optional[str]:
        if not str(raw or "").startswith("/"):
            return None

        parts = raw[1:].split(maxsplit=1)
        name = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        cmd = self._commands.get(name)
        if not cmd:
            return f"Unknown command: /{name}. Type /help for available commands."
        return await cmd.handler(args=args, context=context)

