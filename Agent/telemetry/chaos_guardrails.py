
import logging
import time
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class GuardrailLimits:
    """Cost and blast radius protection limits."""
    max_tokens_per_session: int = 50000
    max_retries_per_request: int = 5
    max_session_duration_seconds: int = 300
    max_consecutive_failures: int = 10

class ChaosGuardrails:
    """Enforces cost and blast radius protection during chaos experiments."""
    
    def __init__(self, limits: Optional[GuardrailLimits] = None):
        self.limits = limits or GuardrailLimits()
        self.session_start_time = time.time()
        self.total_tokens_used = 0
        self.consecutive_failures = 0
        self.emergency_stop_triggered = False
        
    def reset_session(self):
        """Reset session-level counters."""
        self.session_start_time = time.time()
        self.total_tokens_used = 0
        self.consecutive_failures = 0
        self.emergency_stop_triggered = False
        
    def check_token_budget(self, tokens_in: int, tokens_out: int) -> bool:
        """Check if token usage is within budget."""
        self.total_tokens_used += (tokens_in + tokens_out)
        
        if self.total_tokens_used >= self.limits.max_tokens_per_session:
            logger.error(f"🚨 GUARDRAIL: Token budget exceeded ({self.total_tokens_used}/{self.limits.max_tokens_per_session})")
            self.emergency_stop_triggered = True
            return False
        
        if self.total_tokens_used >= self.limits.max_tokens_per_session * 0.8:
            logger.warning(f"⚠️ GUARDRAIL: Token budget at 80% ({self.total_tokens_used}/{self.limits.max_tokens_per_session})")
        
        return True
    
    def check_retry_limit(self, retry_count: int) -> bool:
        """Check if retry count is within limit."""
        if retry_count >= self.limits.max_retries_per_request:
            logger.error(f"🚨 GUARDRAIL: Retry limit exceeded ({retry_count}/{self.limits.max_retries_per_request})")
            self.emergency_stop_triggered = True
            return False
        return True
    
    def check_session_duration(self) -> bool:
        """Check if session duration is within limit."""
        elapsed = time.time() - self.session_start_time
        
        if elapsed >= self.limits.max_session_duration_seconds:
            logger.error(f"🚨 GUARDRAIL: Session duration exceeded ({elapsed:.0f}s/{self.limits.max_session_duration_seconds}s)")
            self.emergency_stop_triggered = True
            return False
        
        if elapsed >= self.limits.max_session_duration_seconds * 0.8:
            logger.warning(f"⚠️ GUARDRAIL: Session duration at 80% ({elapsed:.0f}s/{self.limits.max_session_duration_seconds}s)")
        
        return True
    
    def record_failure(self):
        """Record a failure and check consecutive failure limit."""
        self.consecutive_failures += 1
        
        if self.consecutive_failures >= self.limits.max_consecutive_failures:
            logger.error(f"🚨 GUARDRAIL: Consecutive failure limit exceeded ({self.consecutive_failures}/{self.limits.max_consecutive_failures})")
            self.emergency_stop_triggered = True
            return False
        return True
    
    def record_success(self):
        """Reset consecutive failure counter on success."""
        self.consecutive_failures = 0
    
    def should_stop(self) -> bool:
        """Check if emergency stop has been triggered."""
        return self.emergency_stop_triggered
    
    def get_status(self) -> dict:
        """Get current guardrail status."""
        elapsed = time.time() - self.session_start_time
        return {
            'tokens_used': self.total_tokens_used,
            'tokens_limit': self.limits.max_tokens_per_session,
            'tokens_remaining': self.limits.max_tokens_per_session - self.total_tokens_used,
            'session_duration': elapsed,
            'session_limit': self.limits.max_session_duration_seconds,
            'consecutive_failures': self.consecutive_failures,
            'emergency_stop': self.emergency_stop_triggered
        }

# Singleton instance
_guardrails_instance = None

def get_chaos_guardrails() -> ChaosGuardrails:
    """Get or create the singleton guardrails instance."""
    global _guardrails_instance
    if _guardrails_instance is None:
        _guardrails_instance = ChaosGuardrails()
    return _guardrails_instance

def reset_chaos_guardrails(limits: Optional[GuardrailLimits] = None):
    """Reset the guardrails instance with new limits."""
    global _guardrails_instance
    _guardrails_instance = ChaosGuardrails(limits)
    return _guardrails_instance
