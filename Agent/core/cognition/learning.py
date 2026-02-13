"""
Outcome-Based Learning
Learns from execution outcomes to improve future decisions.
"""
import logging
from typing import Dict, Any, List
from datetime import datetime
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class OutcomeLearner:
    """
    Tracks execution outcomes and adjusts strategies based on results.
    """
    
    def __init__(self, storage_path: str = "data/outcomes.json"):
        self.storage_path = Path(storage_path)
        self.outcomes: List[Dict[str, Any]] = []
        self._load_outcomes()
    
    def record_outcome(self,
                      action: str,
                      tool_name: str,
                      success: bool,
                      context: Dict[str, Any],
                      result: Any = None,
                      error: str = None) -> None:
        """
        Record an execution outcome.
        
        Args:
            action: The action taken
            tool_name: Tool used
            success: Whether it succeeded
            context: Execution context
            result: Result if successful
            error: Error message if failed
        """
        outcome = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "tool_name": tool_name,
            "success": success,
            "context": context,
            "result": str(result) if result else None,
            "error": error
        }
        
        self.outcomes.append(outcome)
        logger.info(f"📝 Recorded outcome: {tool_name} -> {'✅' if success else '❌'}")
        
        # Persist to disk
        self._save_outcomes()
    
    def get_success_rate(self, tool_name: str, context_filter: Dict[str, Any] = None) -> float:
        """
        Get historical success rate for a tool.
        
        Args:
            tool_name: Tool to analyze
            context_filter: Optional context filters
            
        Returns:
            Success rate (0.0 to 1.0)
        """
        relevant_outcomes = [
            o for o in self.outcomes 
            if o['tool_name'] == tool_name
        ]
        
        if context_filter:
            relevant_outcomes = [
                o for o in relevant_outcomes
                if self._matches_context(o['context'], context_filter)
            ]
        
        if not relevant_outcomes:
            return 0.5  # Neutral prior
        
        successes = sum(1 for o in relevant_outcomes if o['success'])
        return successes / len(relevant_outcomes)
    
    def get_recommendations(self, tool_name: str) -> List[str]:
        """
        Get recommendations based on past outcomes.
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Analyze failure patterns
        failures = [o for o in self.outcomes if o['tool_name'] == tool_name and not o['success']]
        
        if len(failures) > 3:
            common_errors = {}
            for failure in failures:
                error = failure.get('error', 'Unknown')
                common_errors[error] = common_errors.get(error, 0) + 1
            
            most_common = max(common_errors.items(), key=lambda x: x[1])
            recommendations.append(f"Watch out for: {most_common[0]} (occurred {most_common[1]} times)")
        
        # Check success rate
        success_rate = self.get_success_rate(tool_name)
        if success_rate < 0.5:
            recommendations.append(f"This tool has a low success rate ({success_rate:.1%}). Consider alternatives.")
        elif success_rate > 0.9:
            recommendations.append(f"This tool is highly reliable ({success_rate:.1%})")
        
        return recommendations
    
    def _matches_context(self, outcome_context: Dict[str, Any], filter_context: Dict[str, Any]) -> bool:
        """Check if outcome context matches filter"""
        for key, value in filter_context.items():
            if outcome_context.get(key) != value:
                return False
        return True
    
    def _load_outcomes(self) -> None:
        """Load outcomes from disk"""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r') as f:
                    self.outcomes = json.load(f)
                logger.info(f"📚 Loaded {len(self.outcomes)} historical outcomes")
        except Exception as e:
            logger.warning(f"⚠️ Could not load outcomes: {e}")
            self.outcomes = []
    
    def _save_outcomes(self) -> None:
        """Save outcomes to disk"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, 'w') as f:
                json.dump(self.outcomes, f, indent=2)
        except Exception as e:
            logger.warning(f"⚠️ Could not save outcomes: {e}")

# Global instance
outcome_learner = OutcomeLearner()
