"""
Input Sanitizer - Prevent injection attacks and validate inputs.
"""
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class InputSanitizer:
    """Sanitizes and validates user inputs."""
    
    # Dangerous patterns to block
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # XSS
        r'javascript:',  # JavaScript protocol
        r'on\w+\s*=',  # Event handlers
        r'eval\s*\(',  # Code execution
        r'exec\s*\(',  # Code execution
        r'__import__',  # Python imports
        r'DROP\s+TABLE',  # SQL injection (case insensitive)
        r'DELETE\s+FROM',  # SQL injection
        r'INSERT\s+INTO',  # SQL injection
    ]
    
    @staticmethod
    def sanitize_string(text: str, max_length: int = 10000) -> str:
        """Sanitize a string input."""
        if not isinstance(text, str):
            return str(text)
        
        # Truncate if too long
        if len(text) > max_length:
            logger.warning(f"⚠️ Input truncated from {len(text)} to {max_length} chars")
            text = text[:max_length]
        
        # Check for dangerous patterns
        for pattern in InputSanitizer.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.error(f"🚨 Blocked dangerous pattern: {pattern}")
                raise ValueError(f"Input contains prohibited pattern")
        
        return text.strip()
    
    @staticmethod
    def sanitize_dict(data: Dict[str, Any], max_depth: int = 5) -> Dict[str, Any]:
        """Recursively sanitize dictionary values."""
        if max_depth <= 0:
            logger.warning("⚠️ Max recursion depth reached in sanitize_dict")
            return {}
        
        sanitized = {}
        for key, value in data.items():
            # Sanitize key
            clean_key = InputSanitizer.sanitize_string(str(key), max_length=100)
            
            # Sanitize value based on type
            if isinstance(value, str):
                sanitized[clean_key] = InputSanitizer.sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[clean_key] = InputSanitizer.sanitize_dict(value, max_depth - 1)
            elif isinstance(value, list):
                sanitized[clean_key] = [
                    InputSanitizer.sanitize_string(str(item)) 
                    if isinstance(item, str) else item
                    for item in value[:100]  # Limit list size
                ]
            else:
                sanitized[clean_key] = value
        
        return sanitized
    
    @staticmethod
    def validate_user_id(user_id: str) -> bool:
        """Validate user ID format (UUID)."""
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(uuid_pattern, user_id, re.IGNORECASE))
    
    @staticmethod
    def validate_session_id(session_id: str) -> bool:
        """Validate session ID format."""
        # Allow alphanumeric and hyphens, max 100 chars
        return bool(re.match(r'^[a-zA-Z0-9\-]{1,100}$', session_id))

# Global sanitizer instance
sanitizer = InputSanitizer()
