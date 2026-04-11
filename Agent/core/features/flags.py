from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class FeatureFlag(str, Enum):
    PROACTIVE = "PROACTIVE"
    KAIROS = "KAIROS"
    VOICE_MODE = "VOICE_MODE"
    TEAM_MODE = "TEAM_MODE"
    RALPH_MODE = "RALPH_MODE"
    BUDDY_FULL = "BUDDY_FULL"
    PLUGIN_LOAD = "PLUGIN_LOAD"
    DREAM_CYCLE = "DREAM_CYCLE"
    AGENT_PETS = "AGENT_PETS"


_LOCKED_FLAGS = {FeatureFlag.AGENT_PETS}

_DEFAULT_STATE: Dict[FeatureFlag, bool] = {
    FeatureFlag.PROACTIVE: False,
    FeatureFlag.KAIROS: False,
    FeatureFlag.VOICE_MODE: False,
    FeatureFlag.TEAM_MODE: True,
    FeatureFlag.RALPH_MODE: True,
    FeatureFlag.BUDDY_FULL: True,
    FeatureFlag.PLUGIN_LOAD: True,
    FeatureFlag.DREAM_CYCLE: False,
    FeatureFlag.AGENT_PETS: False,
}


class FeatureLocked(RuntimeError):
    pass


class FeatureFlagSystem:
    def __init__(self, config_path: Optional[Path] = None):
        self._path = config_path or (Path.home() / ".maya" / "feature_flags.json")
        self._flags: Dict[FeatureFlag, bool] = self._load()

    def is_enabled(self, flag: FeatureFlag) -> bool:
        return self._flags.get(flag, False)

    def all_flags(self) -> Dict[FeatureFlag, bool]:
        return dict(self._flags)

    def enable(self, flag: FeatureFlag) -> None:
        if flag in _LOCKED_FLAGS:
            raise FeatureLocked(
                f"{flag.value} is locked until Phase 39. "
                "It will unlock after the Agent Pets prerequisite phases complete."
            )
        self._flags[flag] = True
        self._persist()

    def disable(self, flag: FeatureFlag) -> None:
        self._flags[flag] = False
        self._persist()

    def reset_to_defaults(self) -> None:
        self._flags = dict(_DEFAULT_STATE)
        self._persist()

    def _load(self) -> Dict[FeatureFlag, bool]:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                loaded = {
                    FeatureFlag(k): bool(v)
                    for k, v in raw.items()
                    if k in FeatureFlag._value2member_map_
                }
                merged = dict(_DEFAULT_STATE)
                merged.update(loaded)
                return merged
            except Exception:
                pass
        return dict(_DEFAULT_STATE)

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({k.value: v for k, v in self._flags.items()}, indent=2)
        )

