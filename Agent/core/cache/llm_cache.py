"""
LLM Response Cache - Reduce costs by caching common queries.
"""
import logging
import hashlib
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class LLMCache:
    """In-memory cache for LLM responses."""
    
    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
    
    def _generate_key(self, messages: list, model: str) -> str:
        """Generate cache key from messages and model."""
        # Create deterministic hash from messages
        content = json.dumps(messages, sort_keys=True) + model
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get(self, messages: list, model: str) -> Optional[str]:
        """Get cached response if available and not expired."""
        key = self._generate_key(messages, model)
        
        if key in self.cache:
            entry = self.cache[key]
            expires_at = entry['timestamp'] + timedelta(seconds=self.ttl_seconds)
            
            if datetime.utcnow() < expires_at:
                self.hits += 1
                logger.info(f"✅ Cache HIT (hit rate: {self.hit_rate():.1%})")
                return entry['response']
            else:
                # Expired, remove from cache
                del self.cache[key]
        
        self.misses += 1
        logger.debug(f"❌ Cache MISS (hit rate: {self.hit_rate():.1%})")
        return None
    
    def set(self, messages: list, model: str, response: str):
        """Cache an LLM response."""
        key = self._generate_key(messages, model)
        
        # Evict oldest if at max size
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
        
        self.cache[key] = {
            'response': response,
            'timestamp': datetime.utcnow()
        }
        logger.debug(f"💾 Cached response (cache size: {len(self.cache)})")
    
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def clear(self):
        """Clear all cached responses."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info("🗑️ Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hit_rate(),
            "ttl_seconds": self.ttl_seconds
        }

# Global cache instance
llm_cache = LLMCache()
