"""
Skill Definition Format
Standard structure for Maya-One plugins/skills.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional
from enum import Enum

class PermissionLevel(Enum):
    """Permission levels for skills"""
    SAFE = "safe"           # No system access
    STORAGE = "storage"      # Read/write user data
    NETWORK = "network"      # Network access
    SYSTEM = "system"        # System commands
    ADMIN = "admin"          # Full system access

@dataclass
class SkillMetadata:
    """Metadata for a skill package"""
    name: str
    version: str
    description: str
    author: str
    permissions: List[PermissionLevel]
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
@dataclass
class SkillFunction:
    """A callable function within a skill"""
    name: str
    description: str
    handler: Callable
    parameters: Dict[str, Any]
    required_params: List[str] = field(default_factory=list)
    
@dataclass
class Skill:
    """Complete skill package"""
    metadata: SkillMetadata
    functions: List[SkillFunction]
    init_handler: Optional[Callable] = None
    cleanup_handler: Optional[Callable] = None
    
    def validate(self) -> bool:
        """Validate skill structure"""
        if not self.metadata.name:
            return False
        if not self.functions:
            return False
        return True
