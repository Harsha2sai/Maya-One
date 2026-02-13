"""
Tool Result Cache - Cache deterministic tool results.
"""
import logging
import hashlib
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ToolCache:
    """Cache for deterministic tool results (weather, time, etc.)."""
    
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        # Different TTLs for different tool types
        self.ttl_config = {
            "get_current_time": 1,  # 1 second
            "get_current_date": 60,  # 1 minute
            "get_weather": 1800,  # 30 minutes
            "search_web": 3600,  # 1 hour
            "default": 300  # 5 minutes
        }
    
    def _generate_key(self, tool_name: str, params: Dict) -> str:
        """Generate cache key from tool name and parameters."""
        content = tool_name + json.dumps(params, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get(self, tool_name: str, params: Dict) -> Optional[Any]:
        """Get cached tool result if available and not expired."""
        key = self._generate_key(tool_name, params)
        
        if key in self.cache:
            entry = self.cache[key]
            ttl = self.ttl_config.get(tool_name, self.ttl_config["default"])
            expires_at = entry['timestamp'] + timedelta(seconds=ttl)
            
            if datetime.utcnow() < expires_at:
                logger.debug(f"✅ Tool cache HIT: {tool_name}")
                return entry['result']
            else:
                del self.cache[key]
        
        logger.debug(f"❌ Tool cache MISS: {tool_name}")
        return None
    
    def set(self, tool_name: str, params: Dict, result: Any):
        """Cache a tool result."""
        key = self._generate_key(tool_name, params)
        
        self.cache[key] = {
            'result': result,
            'timestamp': datetime.utcnow(),
            'tool_name': tool_name
        }
        logger.debug(f"💾 Cached tool result: {tool_name}")
    
    def invalidate(self, tool_name: Optional[str] = None):
        """Invalidate cache entries for a specific tool or all tools."""
        if tool_name:
            keys_to_delete = [
                k for k, v in self.cache.items() 
                if v['tool_name'] == tool_name
            ]
            for key in keys_to_delete:
                del self.cache[key]
            logger.info(f"🗑️ Invalidated cache for tool: {tool_name}")
        else:
            self.cache.clear()
            logger.info("🗑️ Cleared all tool cache")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        tool_counts = {}
        for entry in self.cache.values():
            tool_name = entry['tool_name']
            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
        
        return {
            "total_entries": len(self.cache),
            "by_tool": tool_counts,
            "ttl_config": self.ttl_config
        }

# Global tool cache instance
tool_cache = ToolCache()
