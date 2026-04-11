from __future__ import annotations

from pathlib import Path

import pytest

from core.features.flags import FeatureFlag, FeatureFlagSystem, FeatureLocked


@pytest.fixture
def flags(tmp_path: Path) -> FeatureFlagSystem:
    return FeatureFlagSystem(config_path=tmp_path / "flags.json")


def test_defaults_loaded(flags: FeatureFlagSystem):
    assert flags.is_enabled(FeatureFlag.TEAM_MODE) is True
    assert flags.is_enabled(FeatureFlag.PROACTIVE) is False


def test_enable_and_persist(flags: FeatureFlagSystem, tmp_path: Path):
    flags.enable(FeatureFlag.PROACTIVE)
    assert flags.is_enabled(FeatureFlag.PROACTIVE) is True
    flags2 = FeatureFlagSystem(config_path=tmp_path / "flags.json")
    assert flags2.is_enabled(FeatureFlag.PROACTIVE) is True


def test_disable(flags: FeatureFlagSystem):
    flags.disable(FeatureFlag.TEAM_MODE)
    assert flags.is_enabled(FeatureFlag.TEAM_MODE) is False


def test_agent_pets_locked(flags: FeatureFlagSystem):
    with pytest.raises(FeatureLocked):
        flags.enable(FeatureFlag.AGENT_PETS)


def test_agent_pets_stays_off(flags: FeatureFlagSystem):
    try:
        flags.enable(FeatureFlag.AGENT_PETS)
    except FeatureLocked:
        pass
    assert flags.is_enabled(FeatureFlag.AGENT_PETS) is False


def test_reset_to_defaults(flags: FeatureFlagSystem):
    flags.enable(FeatureFlag.PROACTIVE)
    flags.reset_to_defaults()
    assert flags.is_enabled(FeatureFlag.PROACTIVE) is False
    assert flags.is_enabled(FeatureFlag.TEAM_MODE) is True


def test_all_flags_returns_full_dict(flags: FeatureFlagSystem):
    result = flags.all_flags()
    assert len(result) == len(FeatureFlag)
    assert all(isinstance(v, bool) for v in result.values())


def test_unknown_key_in_file_ignored(tmp_path: Path):
    path = tmp_path / "flags.json"
    path.write_text('{"UNKNOWN_FLAG": true, "PROACTIVE": true}', encoding="utf-8")
    loaded = FeatureFlagSystem(config_path=path)
    assert loaded.is_enabled(FeatureFlag.PROACTIVE) is True

