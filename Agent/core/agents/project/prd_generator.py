"""Project requirements to PRD generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .clarification import RequirementsState


@dataclass
class PRD:
    title: str
    overview: str
    goals: List[str] = field(default_factory=list)
    non_goals: List[str] = field(default_factory=list)
    technical_requirements: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "title": self.title,
            "overview": self.overview,
            "goals": list(self.goals),
            "non_goals": list(self.non_goals),
            "technical_requirements": list(self.technical_requirements),
            "open_questions": list(self.open_questions),
        }


class PRDGenerator:
    """Generate structured PRD dataclass from completed requirements state."""

    def generate(self, requirements: RequirementsState) -> PRD:
        question_map = {item.question_id: item for item in requirements.questions}

        title_source = requirements.raw_description or "Project"
        title = self._derive_title(title_source)
        overview = requirements.raw_description or "Project requirements captured through clarification workflow."

        goals = self._collect_answer(question_map, "q_goal")
        users = self._collect_answer(question_map, "q_users")
        scope = self._collect_answer(question_map, "q_scope")
        if users:
            goals.append(f"Serve primary users: {users[0]}")
        if scope:
            goals.append(f"Deliver v1 scope: {scope[0]}")

        non_goals = self._collect_answer(question_map, "q_nongoals")

        technical_requirements: List[str] = []
        technical_requirements.extend(self._collect_answer(question_map, "q_constraints"))
        technical_requirements.extend(self._collect_answer(question_map, "q_mobile_platforms"))
        technical_requirements.extend(self._collect_answer(question_map, "q_web_stack"))
        technical_requirements.extend(self._collect_answer(question_map, "q_ai_policy"))
        technical_requirements.extend(self._collect_answer(question_map, "q_timeline"))

        open_questions = [
            item.text for item in requirements.questions if not str(item.answer or "").strip()
        ]

        return PRD(
            title=title,
            overview=overview,
            goals=goals,
            non_goals=non_goals,
            technical_requirements=technical_requirements,
            open_questions=open_questions,
        )

    @staticmethod
    def _collect_answer(question_map: Dict[str, object], key: str) -> List[str]:
        item = question_map.get(key)
        if item is None:
            return []
        answer = str(getattr(item, "answer", "") or "").strip()
        if not answer:
            return []
        return [answer]

    @staticmethod
    def _derive_title(raw_description: str) -> str:
        text = str(raw_description or "").strip()
        if not text:
            return "Project Requirements Document"
        words = text.split()
        if len(words) <= 8:
            stem = " ".join(words)
        else:
            stem = " ".join(words[:8]) + "..."
        return f"PRD: {stem}"
