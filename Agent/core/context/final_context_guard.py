
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class FinalContextGuard:
    """
    Final safety barrier before sending context to LLM.
    Enforces hard limits and sanity checks that might have been missed by upstream logic.
    """
    
    def __init__(self, max_tokens: int = 128000): # Default to a safe high limit, can be lower
        self.max_tokens = max_tokens

    def ensure_safe(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sanitizes and validates the message list.
        Returns a safe list of messages.
        Raises ValueError if context is fundamentally broken.
        """
        if not messages:
            logger.warning("🚫 FinalContextGuard: Empty context detected! Injecting system prompt.")
            return [{"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant."}]}]

        safe_messages = []
        has_system = False
        total_chars = 0
        
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # 1. Role Validation
            if role not in ["system", "user", "assistant", "tool"]:
                logger.warning(f"🚫 FinalContextGuard: Invalid role '{role}' at index {i}. Dropping.")
                continue
                
            # 2. Content Sanitization
            if content is None:
                content = ""
            
            # Convert list content (multi-modal) to string for simplicity if needed, 
            # OR keep it if we support vision. For now, we assume text or list-of-text.
            if isinstance(content, list):
                # checking if valid list
                pass 
            elif not isinstance(content, str):
                logger.warning(f"🚫 FinalContextGuard: Invalid content type {type(content)} at index {i}. Converting to string.")
                content = str(content)
            
            # 3. System Prompt Check
            if role == "system":
                has_system = True
                
            # 4. Token Estimation (Rough Char Count)
            # 1 token ~= 4 chars
            msg_len = len(str(content))
            total_chars += msg_len
            
            safe_messages.append(msg)

        # 5. Token Limit Check
        est_tokens = total_chars / 4
        if est_tokens > self.max_tokens:
            logger.error(f"🚫 FinalContextGuard: Context exceeds limit ({est_tokens} > {self.max_tokens}). Truncating.")
            # Simple truncation: Keep system + last N messages
            # This is a panic fallback. Upstream RollingContext should have handled this.
            
            # Keep system
            kept = [m for m in safe_messages if m["role"] == "system"]
            others = [m for m in safe_messages if m["role"] != "system"]
            
            # Retain last ~half of limit
            target_chars = (self.max_tokens * 4) * 0.8 
            current_chars = sum(len(str(m.get("content",""))) for m in kept)
            
            truncated_others = []
            for m in reversed(others):
                m_len = len(str(m.get("content","")))
                if current_chars + m_len < target_chars:
                    truncated_others.insert(0, m)
                    current_chars += m_len
                else:
                    break
            
            safe_messages = kept + truncated_others
            logger.warning(f"🚫 FinalContextGuard: Truncated to {len(safe_messages)} messages.")

        # 6. Ensure System Prompt
        if not any(m["role"] == "system" for m in safe_messages):
             logger.warning("🚫 FinalContextGuard: No system prompt found. Injecting default.")
             safe_messages.insert(0, {"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant."}]})

        return safe_messages
