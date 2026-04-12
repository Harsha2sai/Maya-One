"""PetRegistry for tracking all pets across subagents."""
from __future__ import annotations

from typing import Dict, List, Optional

from .pet import AgentPet
from .types import PetType

MAX_PETS_PER_AGENT = 5


class PetRegistry:
    """Tracks all pets across all subagents."""

    def __init__(self):
        self._pets: Dict[str, AgentPet] = {}  # pet_id → pet
        self._by_parent: Dict[str, List[str]] = {}  # parent_type → [pet_ids]

    def spawn_pet(self, pet_type: PetType, parent_agent_type: str) -> AgentPet:
        """
        Spawn a new pet for a parent agent.

        Args:
            pet_type: The type of pet to spawn.
            parent_agent_type: The type of the parent agent.

        Returns:
            The spawned pet.

        Raises:
            ValueError: If max pets per agent exceeded.
        """
        existing = self._by_parent.get(parent_agent_type, [])
        if len(existing) >= MAX_PETS_PER_AGENT:
            raise ValueError(f"Max {MAX_PETS_PER_AGENT} pets per agent")

        pet = AgentPet(pet_type=pet_type, parent_agent_type=parent_agent_type)
        self._pets[pet.instance.id] = pet
        self._by_parent.setdefault(parent_agent_type, []).append(pet.instance.id)
        return pet

    def get_pet(self, pet_id: str) -> Optional[AgentPet]:
        """Get a pet by ID."""
        return self._pets.get(pet_id)

    def list_pets(self, parent_agent_type: Optional[str] = None) -> List[AgentPet]:
        """
        List pets, optionally filtered by parent agent type.

        Args:
            parent_agent_type: If provided, only return pets for this parent.

        Returns:
            List of pets.
        """
        if parent_agent_type:
            ids = self._by_parent.get(parent_agent_type, [])
            return [self._pets[i] for i in ids if i in self._pets]
        return list(self._pets.values())

    def summary(self) -> str:
        """Get a formatted summary of all pets."""
        if not self._pets:
            return "🐾 No pets yet."
        lines = ["🐾 Pet Collection:"]
        for pet in self._pets.values():
            lines.append(f"  {pet.summary}")
        return "\n".join(lines)
