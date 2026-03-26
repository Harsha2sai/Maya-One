"""
Self-Reflection Module
Enables the agent to evaluate its own reasoning and decisions.
"""
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ReflectionType(Enum):
    """Types of reflection"""
    PRE_ACTION = "pre_action"      # Before executing
    POST_ACTION = "post_action"    # After execution
    ERROR_ANALYSIS = "error"        # After failures
    STRATEGY_REVIEW = "strategy"    # Periodic review

@dataclass
class ReflectionResult:
    """Result of self-reflection"""
    should_proceed: bool
    confidence: float
    concerns: List[str]
    suggestions: List[str]
    reasoning: str

class SelfReflectionEngine:
    """
    Implements meta-cognitive capabilities.
    Agent reasons about its own plans and decisions.
    """
    
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
        self.error_patterns: List[Dict[str, Any]] = []
    
    async def reflect_on_action(self, 
                                 action: str, 
                                 context: Dict[str, Any],
                                 tool_name: Optional[str] = None) -> ReflectionResult:
        """
        Reflect on a planned action before execution.
        
        Args:
            action: The action being considered
            context: Current context
            tool_name: Tool to be used (if any)
            
        Returns:
            ReflectionResult with evaluation
        """
        concerns = []
        suggestions = []
        confidence = 0.8  # Default
        
        # 1. Check for common error patterns
        if self._matches_error_pattern(action, tool_name):
            concerns.append("This action has failed before in similar contexts")
            confidence -= 0.3
        
        # 2. Verify tool parameters if applicable
        if tool_name and context.get('parameters'):
            if not self._validate_parameters(tool_name, context['parameters']):
                concerns.append("Missing or invalid parameters detected")
                suggestions.append("Clarify parameter values before proceeding")
                confidence -= 0.4
        
        # 3. Check for risky operations
        risk_keywords = ['delete', 'remove', 'kill', 'destroy', 'wipe']
        if any(keyword in action.lower() for keyword in risk_keywords):
            concerns.append("This is a potentially destructive operation")
            suggestions.append("Confirm with the user before proceeding")
            confidence -= 0.2
        
        # 4. Determine if should proceed
        should_proceed = confidence > 0.5 and len(concerns) == 0
        
        reasoning = self._generate_reasoning(action, concerns, suggestions)
        
        logger.info(f"🤔 Reflection on '{action}': proceed={should_proceed}, confidence={confidence:.2f}")
        
        return ReflectionResult(
            should_proceed=should_proceed,
            confidence=confidence,
            concerns=concerns,
            suggestions=suggestions,
            reasoning=reasoning
        )
    
    async def analyze_error(self, 
                           action: str,
                           error: str,
                           context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze an error to learn from it.
        
        Returns:
            Analysis with root cause and recommendations
        """
        logger.info(f"🔍 Analyzing error: {error}")
        
        # Store error pattern
        error_pattern = {
            "action": action,
            "error": error,
            "context": context
        }
        self.error_patterns.append(error_pattern)
        
        # Basic root cause analysis
        root_cause = "Unknown"
        if "permission" in error.lower():
            root_cause = "Insufficient permissions"
        elif "not found" in error.lower():
            root_cause = "Resource not available"
        elif "timeout" in error.lower():
            root_cause = "Operation timed out"
        
        return {
            "root_cause": root_cause,
            "recommendation": "Revise approach or request user intervention"
        }
    
    def _matches_error_pattern(self, action: str, tool_name: Optional[str]) -> bool:
        """Check if this action matches a known failure pattern"""
        for pattern in self.error_patterns:
            if tool_name and pattern.get('context', {}).get('tool_name') == tool_name:
                if action.lower() in pattern['action'].lower():
                    return True
        return False
    
    def _validate_parameters(self, tool_name: str, params: Dict[str, Any]) -> bool:
        """Basic parameter validation"""
        # This would integrate with tool registry for schema validation
        return bool(params)
    
    def _generate_reasoning(self, action: str, concerns: List[str], suggestions: List[str]) -> str:
        """Generate human-readable reasoning"""
        if not concerns:
            return f"Action '{action}' appears safe to proceed."
        
        reasoning = f"Evaluating '{action}':\n"
        for concern in concerns:
            reasoning += f"- Concern: {concern}\n"
        for suggestion in suggestions:
            reasoning += f"- Suggestion: {suggestion}\n"
        
        return reasoning

# Global instance
reflection_engine = SelfReflectionEngine()
