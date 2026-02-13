"""
Tool Registry Module
Automatically discovers and registers tools from MCP servers.
Provides metadata storage and semantic matching for tool selection.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """Metadata for a registered tool"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    required_params: List[str] = field(default_factory=list)
    action_keywords: List[str] = field(default_factory=list)
    category: str = "general"
    
    def __post_init__(self):
        """Extract action keywords from description"""
        if not self.action_keywords:
            self.action_keywords = self._extract_keywords()
    
    def _extract_keywords(self) -> List[str]:
        """Extract action keywords from tool name and description"""
        keywords = []
        
        # Extract from name (e.g., "Play_music_in_Spotify" -> ["play", "music", "spotify"])
        name_parts = re.split(r'[_\s]+', self.name.lower())
        keywords.extend([p for p in name_parts if len(p) > 2])
        
        # Extract action verbs from description using word boundaries
        action_verbs = [
            'play', 'pause', 'stop', 'skip', 'search', 'find', 'get', 'set',
            'add', 'remove', 'delete', 'create', 'send', 'check', 'show',
            'list', 'queue', 'like', 'save', 'open', 'start', 'resume'
        ]
        desc_lower = self.description.lower()
        for verb in action_verbs:
            # Use word boundaries to avoid false positives (e.g., 'play' in 'display')
            if re.search(r'\b' + re.escape(verb) + r'\b', desc_lower):
                keywords.append(verb)
        
        return list(set(keywords))


class ToolRegistry:
    """
    Registry for tool metadata with auto-discovery and matching capabilities.
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}
        self._categories: Dict[str, List[str]] = {}
        self.logger = logging.getLogger(__name__)
    
    @property
    def tool_count(self) -> int:
        return len(self._tools)
    
    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())
    
    def register_tool(self, metadata: ToolMetadata) -> None:
        """Register a single tool"""
        # Handle re-registration: remove from old category first
        if metadata.name in self._tools:
            old_category = self._tools[metadata.name].category
            if old_category in self._categories and metadata.name in self._categories[old_category]:
                self._categories[old_category].remove(metadata.name)
        
        self._tools[metadata.name] = metadata
        
        # Organize by category (prevent duplicates)
        if metadata.category not in self._categories:
            self._categories[metadata.category] = []
        if metadata.name not in self._categories[metadata.category]:
            self._categories[metadata.category].append(metadata.name)
        
        self.logger.debug(f"Registered tool: {metadata.name}")
    
    def register_from_mcp_tools(self, mcp_tools: List[Any]) -> int:
        """
        Register tools from MCP tool list.
        
        Args:
            mcp_tools: List of MCP tool objects
            
        Returns:
            Number of tools registered
        """
        registered = 0
        
        for tool in mcp_tools:
            try:
                # Extract tool info from MCP format
                name = getattr(tool, 'name', None) or tool.get('name', 'unknown')
                description = getattr(tool, 'description', '') or tool.get('description', '')
                
                # Extract parameters
                params = {}
                required = []
                
                if hasattr(tool, 'inputSchema'):
                    schema = tool.inputSchema
                elif hasattr(tool, 'parameters'):
                    schema = tool.parameters
                elif isinstance(tool, dict) and 'inputSchema' in tool:
                    schema = tool['inputSchema']
                else:
                    schema = {}
                
                if isinstance(schema, dict):
                    params = schema.get('properties', {})
                    required = schema.get('required', [])
                
                # Determine category from name
                category = self._infer_category(name, description)
                
                metadata = ToolMetadata(
                    name=name,
                    description=description,
                    parameters=params,
                    required_params=required,
                    category=category
                )
                
                self.register_tool(metadata)
                registered += 1
                
            except Exception as e:
                self.logger.warning(f"Failed to register tool: {e}")
                continue
        
        self.logger.info(f"✅ Registered {registered} tools from MCP")
        return registered
    
    def _infer_category(self, name: str, description: str) -> str:
        """Infer tool category from name and description"""
        text = (name + " " + description).lower()
        
        categories = {
            'music': ['spotify', 'music', 'song', 'track', 'playlist', 'play', 'pause', 'skip'],
            'weather': ['weather', 'temperature', 'forecast', 'climate'],
            'communication': ['email', 'send', 'message', 'notify'],
            'search': ['search', 'find', 'lookup', 'query', 'web'],
            'time': ['time', 'current', 'now', 'today', 'clock'],
            'calendar': ['calendar', 'event', 'appointment', 'schedule', 'meeting'],
            'alarms': ['alarm', 'alarms', 'wake'],
            'reminders': ['reminder', 'reminders'],
            'memory': ['remember', 'recall', 'memory', 'store'],
            'notes': ['note', 'notes'],
        }
        
        for category, keywords in categories.items():
            if any(kw in text for kw in keywords):
                return category
        
        return 'general'
    
    def get_tool(self, name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name"""
        return self._tools.get(name)
    
    def get_tools_by_category(self, category: str) -> List[ToolMetadata]:
        """Get all tools in a category"""
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def match_tool(self, user_text: str, top_k: int = 3) -> List[tuple]:
        """
        Match user text to the best matching tools.
        
        Args:
            user_text: User's query
            top_k: Number of top matches to return
            
        Returns:
            List of (tool_name, confidence_score) tuples
        """
        if not self._tools:
            return []
        
        user_lower = user_text.lower()
        user_words = set(re.findall(r'\w+', user_lower))
        
        scores = []
        
        for name, metadata in self._tools.items():
            score = 0.0
            
            # 1. Keyword overlap (0-40 points)
            keyword_matches = len(user_words & set(metadata.action_keywords))
            score += min(keyword_matches * 10, 40)
            
            # 2. Description similarity (0-30 points)
            desc_similarity = SequenceMatcher(
                None, user_lower, metadata.description.lower()
            ).ratio()
            score += desc_similarity * 30
            
            # 3. Name similarity (0-20 points)
            name_clean = metadata.name.lower().replace('_', ' ')
            name_similarity = SequenceMatcher(None, user_lower, name_clean).ratio()
            score += name_similarity * 20
            
            # 4. Category bonus (0-10 points)
            category_keywords = {
                'music': ['play', 'song', 'music', 'track', 'spotify', 'pause', 'skip'],
                'weather': ['weather', 'temperature', 'hot', 'cold', 'rain'],
                'communication': ['email', 'send', 'message'],
                'search': ['search', 'find', 'what', 'who', 'how'],
                'time': ['time', 'date', 'when', 'today', 'now'],
            }
            for cat, kws in category_keywords.items():
                if metadata.category == cat and any(kw in user_lower for kw in kws):
                    score += 10
                    break
            
            if score > 0:
                scores.append((name, score))
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_k]
    
    def get_best_match(self, user_text: str, min_confidence: float = 20.0) -> Optional[str]:
        """
        Get the single best matching tool if confidence is high enough.
        
        Args:
            user_text: User's query
            min_confidence: Minimum score required
            
        Returns:
            Tool name or None
        """
        matches = self.match_tool(user_text, top_k=1)
        
        if matches and matches[0][1] >= min_confidence:
            return matches[0][0]
        
        return None
    
    def get_summary(self) -> str:
        """Get a summary of registered tools"""
        lines = [f"📦 Tool Registry: {self.tool_count} tools"]
        
        for category, tool_names in self._categories.items():
            lines.append(f"  [{category}]: {len(tool_names)} tools")
        
        return "\n".join(lines)
    
    def get_all_tools(self) -> List[ToolMetadata]:
        """Get all registered tool metadata objects"""
        return list(self._tools.values())


# Singleton instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)"""
    global _registry
    _registry = None
