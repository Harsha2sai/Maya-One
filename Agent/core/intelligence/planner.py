
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PlanStep:
    description: str
    tool_name: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    completed: bool = False
    result: Optional[str] = None

class TaskPlanner:
    """
    Handles decomposition of complex goals into actionable steps.
    Tracks state and facilitates multi-step execution.
    """
    def __init__(self):
        self.current_plan: List[PlanStep] = []
        self.goal: str = ""
        self.is_active: bool = False

    def create_plan(self, goal: str, steps: List[Dict[str, Any]]) -> None:
        """Initialize a new plan from a list of steps."""
        self.goal = goal
        self.current_plan = [
            PlanStep(
                description=s['description'],
                tool_name=s.get('tool_name'),
                parameters=s.get('parameters', {}),
            ) for s in steps
        ]
        self.is_active = True
        logger.info(f"📋 New plan created for goal: {goal} ({len(self.current_plan)} steps)")

    def get_next_step(self) -> Optional[PlanStep]:
        """Get the next uncompleted step in the plan."""
        for step in self.current_plan:
            if not step.completed:
                return step
        return None

    def mark_step_completed(self, result: str) -> None:
        """Mark the current step as completed and store the result."""
        step = self.get_next_step()
        if step:
            step.completed = True
            step.result = result
            logger.info(f"✅ Step completed: {step.description}")
            
        if all(s.completed for s in self.current_plan):
            self.is_active = False
            logger.info("🏁 Plan fully completed")

    def get_progress_report(self) -> str:
        """Generate a natural language summary of plan progress."""
        completed = sum(1 for s in self.current_plan if s.completed)
        total = len(self.current_plan)
        
        report = f"Progress for '{self.goal}': {completed}/{total} steps done.\n"
        for i, step in enumerate(self.current_plan):
            status = "✅" if step.completed else "⏳"
            report += f"{i+1}. {status} {step.description}\n"
            
        return report

# Global Planner Instance
task_planner = TaskPlanner()
