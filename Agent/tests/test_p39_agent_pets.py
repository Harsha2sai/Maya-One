"""Tests for Agent Pets system (P39)."""
from __future__ import annotations

import pytest

from core.agents.pets import AgentPet, PetRegistry, PET_PROMPTS
from core.agents.pets.registry import MAX_PETS_PER_AGENT
from core.agents.pets.types import PetInstance, PetPersonality, PetType


def test_pet_registry_spawn_creates_pet_with_correct_type_and_parent():
    """PetRegistry.spawn_pet() creates pet with correct type and parent."""
    registry = PetRegistry()
    pet = registry.spawn_pet(PetType.LINT, "coder")

    assert pet.instance.pet_type == PetType.LINT
    assert pet.instance.parent_agent_type == "coder"
    assert pet.instance.id in registry._pets


def test_pet_gain_xp_levels_up_at_correct_threshold():
    """AgentPet.gain_xp() levels up at correct threshold."""
    pet = AgentPet(PetType.TEST, "tester")

    # Level 1 starts at 0 XP
    assert pet.instance.level == 1
    assert pet.instance.xp == 0

    # Gain 49 XP - still level 1
    pet.instance.gain_xp(49)
    assert pet.instance.level == 1

    # Gain 1 more XP - level up to 2
    leveled_up = pet.instance.gain_xp(1)
    assert leveled_up is True
    assert pet.instance.level == 2


def test_pet_build_prompt_includes_level_info_at_level_3_plus():
    """AgentPet._build_prompt() includes level info at level 3+."""
    pet = AgentPet(PetType.SECURITY, "reviewer")

    # Level 1 - no level info
    prompt = pet._build_prompt()
    assert "level" not in prompt.lower()

    # Level 3 - includes level info
    pet.instance.level = 3
    prompt = pet._build_prompt()
    assert "level 3" in prompt


def test_pet_registry_enforces_max_pets_per_agent():
    """PetRegistry enforces MAX_PETS_PER_AGENT."""
    registry = PetRegistry()

    # Spawn max pets
    for _ in range(MAX_PETS_PER_AGENT):
        registry.spawn_pet(PetType.LINT, "coder")

    # Next spawn should raise
    with pytest.raises(ValueError, match="Max 5 pets per agent"):
        registry.spawn_pet(PetType.TEST, "coder")


def test_pet_registry_summary_returns_formatted_string():
    """PetRegistry.summary() returns formatted string."""
    registry = PetRegistry()
    assert "No pets yet" in registry.summary()

    registry.spawn_pet(PetType.LINT, "coder")
    summary = registry.summary()
    assert "Pet Collection" in summary
    assert "lint" in summary


def test_agent_pets_flag_is_no_longer_locked():
    """AGENT_PETS flag is no longer locked."""
    from core.features.flags import _LOCKED_FLAGS, FeatureFlag

    assert FeatureFlag.AGENT_PETS not in _LOCKED_FLAGS


def test_pet_personality_evolution():
    """Pet personality evolves based on task outcomes."""
    pet = AgentPet(PetType.SECURITY, "reviewer")

    initial_caution = pet.instance.personality.caution

    # Security pets become more cautious on success
    pet._evolve_personality(success=True)
    assert pet.instance.personality.caution > initial_caution

    # Pets become more cautious on failure
    initial_thoroughness = pet.instance.personality.thoroughness
    pet._evolve_personality(success=False)
    assert pet.instance.personality.caution > initial_caution


def test_pet_success_rate_calculation():
    """Pet success rate is calculated correctly."""
    pet = AgentPet(PetType.TEST, "tester")

    # No tasks - 100% success rate
    assert pet.instance.success_rate == 1.0

    # 1 success, 1 failure - 50% success rate
    pet.instance.task_count = 2
    pet.instance.success_count = 1
    assert pet.instance.success_rate == 0.5


def test_pet_summary_includes_icon_based_on_level():
    """Pet summary includes icon based on level."""
    pet = AgentPet(PetType.LINT, "coder")

    # Level 1 - egg
    assert "🥚" in pet.summary

    # Level 5 - dragon
    pet.instance.level = 5
    assert "🐉" in pet.summary


def test_pet_prompts_exist_for_all_types():
    """PET_PROMPTS has entries for all PetType values."""
    for pet_type in PetType:
        assert pet_type in PET_PROMPTS
        assert isinstance(PET_PROMPTS[pet_type], str)
        assert len(PET_PROMPTS[pet_type]) > 0
