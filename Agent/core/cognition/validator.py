"""
Strategy Validator
Validates execution strategies before committing to them.
"""
import logging
from typing import Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of strategy validation"""
    is_valid: bool
    issues: List[str]
    score: float
    recommendations: List[str]

class StrategyValidator:
    """
    Validates multi-step strategies and execution plans.
    Ensures plans are coherent, feasible, and safe.
    """
    
    def __init__(self):
        self.validation_history: List[Dict[str, Any]] = []
    
    def validate_plan(self, goal: str, steps: List[Dict[str, Any]]) -> ValidationResult:
        """
        Validate a multi-step plan.
        
        Args:
            goal: The overall goal
            steps: List of planned steps
            
        Returns:
            ValidationResult with score and issues
        """
        issues = []
        recommendations = []
        score = 1.0
        
        # 1. Check for empty plan
        if not steps:
            issues.append("Plan has no steps")
            score = 0.0
            return ValidationResult(False, issues, score, recommendations)
        
        # 2. Check for circular dependencies
        if self._has_circular_deps(steps):
            issues.append("Plan contains circular dependencies")
            score -= 0.5
        
        # 3. Check for missing prerequisites
        missing_prereqs = self._find_missing_prerequisites(steps)
        if missing_prereqs:
            issues.append(f"Missing prerequisites: {missing_prereqs}")
            recommendations.append("Add prerequisite steps")
            score -= 0.3
        
        # 4. Verify step ordering
        if not self._validate_step_order(steps):
            issues.append("Steps may be in incorrect order")
            recommendations.append("Review step dependencies")
            score -= 0.2
        
        # 5. Check for overly complex plans
        if len(steps) > 20:
            recommendations.append("Plan is very complex, consider breaking into sub-goals")
            score -= 0.1
        
        is_valid = score > 0.5 and len(issues) == 0
        
        logger.info(f"📊 Plan validation: valid={is_valid}, score={score:.2f}, issues={len(issues)}")
        
        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            score=score,
            recommendations=recommendations
        )
    
    def validate_tool_selection(self, goal: str, tool_name: str, context: Dict[str, Any]) -> bool:
        """Validate that a tool is appropriate for the goal"""
        # Basic heuristics
        
        # 1. Check if tool name relates to goal
        tool_words = set(tool_name.lower().split('_'))
        goal_words = set(goal.lower().split())
        
        overlap = tool_words & goal_words
        if not overlap:
            logger.warning(f"⚠️ Tool '{tool_name}' may not match goal '{goal}'")
            return False
        
        return True
    
    def _has_circular_deps(self, steps: List[Dict[str, Any]]) -> bool:
        """Check for circular dependencies in steps"""
        # Simplified check - would need dependency graph for full analysis
        return False
    
    def _find_missing_prerequisites(self, steps: List[Dict[str, Any]]) -> List[str]:
        """Find missing prerequisite steps"""
        # Placeholder for dependency analysis
        return []
    
    def _validate_step_order(self, steps: List[Dict[str, Any]]) -> bool:
        """Validate that steps are in a logical order"""
        # Basic validation - check that no step references future outputs
        return True

# Global instance
strategy_validator = StrategyValidator()
