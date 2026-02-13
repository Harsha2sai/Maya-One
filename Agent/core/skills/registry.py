"""
Skill Registry - Dynamic skill loading and management.
"""
import logging
from typing import Dict, List, Optional, Callable
from pathlib import Path
import importlib.util
import sys

from core.skills.schema import Skill, SkillMetadata, PermissionLevel
from core.registry.tool_registry import get_registry, ToolMetadata
from core.governance.types import UserRole

logger = logging.getLogger(__name__)

class SkillRegistry:
    """
    Manages dynamically loaded skills.
    Enforces permissions and integrates with tool registry.
    """
    
    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self.tool_registry = get_registry()
    
    def register_skill(self, skill: Skill, user_role: UserRole = UserRole.GUEST) -> bool:
        """
        Register a skill package.
        
        Args:
            skill: The skill to register
            user_role: User role requesting registration
            
        Returns:
            True if successful
        """
        try:
            # Validate skill structure
            if not skill.validate():
                logger.error(f"❌ Invalid skill structure: {skill.metadata.name}")
                return False
            
            # Check permissions
            if not self._check_permissions(skill, user_role):
                logger.error(f"❌ Insufficient permissions to load skill: {skill.metadata.name}")
                return False
            
            # Initialize skill if handler provided
            if skill.init_handler:
                skill.init_handler()
            
            # Register each function as a tool
            for func in skill.functions:
                tool_meta = ToolMetadata(
                    name=f"{skill.metadata.name}.{func.name}",
                    description=func.description,
                    parameters=func.parameters,
                    required_params=func.required_params,
                    category="skill"
                )
                self.tool_registry.register_tool(tool_meta)
            
            # Store skill
            self.skills[skill.metadata.name] = skill
            logger.info(f"✅ Registered skill: {skill.metadata.name} ({len(skill.functions)} functions)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to register skill {skill.metadata.name}: {e}")
            return False
    
    def _check_permissions(self, skill: Skill, user_role: UserRole) -> bool:
        """Check if user has permissions to load this skill"""
        required_permissions = skill.metadata.permissions
        
        # Only ADMIN can load ADMIN-level skills
        if PermissionLevel.ADMIN in required_permissions:
            return user_role == UserRole.ADMIN
        
        # SYSTEM permissions require at least MEMBER
        if PermissionLevel.SYSTEM in required_permissions:
            return user_role in [UserRole.MEMBER, UserRole.ADMIN]
        
        # SAFE skills can be loaded by anyone
        return True
    
    def load_from_file(self, skill_path: Path, user_role: UserRole = UserRole.GUEST) -> bool:
        """
        Load a skill from a Python file.
        
        The file must define a `create_skill()` function that returns a Skill object.
        """
        try:
            # Import the skill module
            spec = importlib.util.spec_from_file_location("skill_module", skill_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules["skill_module"] = module
            spec.loader.exec_module(module)
            
            # Get the skill object
            if not hasattr(module, 'create_skill'):
                logger.error(f"❌ Skill file missing create_skill() function: {skill_path}")
                return False
            
            skill = module.create_skill()
            return self.register_skill(skill, user_role)
            
        except Exception as e:
            logger.error(f"❌ Failed to load skill from {skill_path}: {e}")
            return False
    
    def unload_skill(self, skill_name: str) -> bool:
        """Unload a skill and remove its functions"""
        if skill_name not in self.skills:
            return False
        
        skill = self.skills[skill_name]
        
        # Call cleanup handler
        if skill.cleanup_handler:
            try:
                skill.cleanup_handler()
            except Exception as e:
                logger.error(f"⚠️ Skill cleanup failed: {e}")
        
        # Remove functions from tool registry
        for func in skill.functions:
            tool_name = f"{skill_name}.{func.name}"
            # Note: Tool registry doesn't have unregister, would need to add
        
        del self.skills[skill_name]
        logger.info(f"🗑️ Unloaded skill: {skill_name}")
        return True
    
    def list_skills(self) -> List[Dict]:
        """Get information about all loaded skills"""
        return [
            {
                "name": skill.metadata.name,
                "version": skill.metadata.version,
                "description": skill.metadata.description,
                "functions": len(skill.functions),
                "permissions": [p.value for p in skill.metadata.permissions]
            }
            for skill in self.skills.values()
        ]

    def get_skill_function(self, tool_name: str) -> Optional[Callable]:
        """Get the handler for a skill function (format: skill_name.func_name)"""
        if "." not in tool_name:
            return None
            
        skill_name, func_name = tool_name.split(".", 1)
        if skill_name in self.skills:
            for func in self.skills[skill_name].functions:
                if func.name == func_name:
                    return func.handler
        return None

# Global registry
_skill_registry: Optional[SkillRegistry] = None

def get_skill_registry() -> SkillRegistry:
    """Get the global skill registry"""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
