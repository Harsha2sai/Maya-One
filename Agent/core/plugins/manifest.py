from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class PluginManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    commands: List[str] = field(default_factory=list)

