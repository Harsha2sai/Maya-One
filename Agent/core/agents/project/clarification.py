"""Requirements clarification helper for project-mode conversations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ClarificationQuestion:
    question_id: str
    text: str
    answer: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "question_id": self.question_id,
            "text": self.text,
            "answer": self.answer,
        }


@dataclass
class RequirementsState:
    raw_description: str
    questions: List[ClarificationQuestion] = field(default_factory=list)
    answered_count: int = 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "raw_description": self.raw_description,
            "questions": [item.to_dict() for item in self.questions],
            "answered_count": self.answered_count,
        }


class RequirementsGatherer:
    """Generates/updates clarification prompts until requirements are complete."""

    def __init__(self, *, min_answered: int = 4) -> None:
        self.min_answered = max(1, int(min_answered))

    def generate_questions(self, raw_description: str) -> List[ClarificationQuestion]:
        normalized = str(raw_description or "").strip()
        if not normalized:
            return [
                ClarificationQuestion("q_goal", "What is the main problem this project should solve?"),
                ClarificationQuestion("q_users", "Who are the primary users?"),
                ClarificationQuestion("q_scope", "What is in scope for the first release?"),
                ClarificationQuestion("q_constraints", "Any technical constraints or required integrations?"),
                ClarificationQuestion("q_timeline", "What timeline or milestone target should we optimize for?"),
            ]

        has_mobile = bool(re.search(r"\b(android|ios|mobile|flutter|app)\b", normalized, flags=re.I))
        has_web = bool(re.search(r"\b(web|website|browser|frontend)\b", normalized, flags=re.I))
        has_ai = bool(re.search(r"\b(ai|llm|agent|ml|gpt)\b", normalized, flags=re.I))

        questions: List[ClarificationQuestion] = [
            ClarificationQuestion("q_goal", "What is the single most important outcome for this project?"),
            ClarificationQuestion("q_users", "Which users/personas should this release serve first?"),
            ClarificationQuestion("q_scope", "What features are must-have vs nice-to-have for v1?"),
            ClarificationQuestion("q_nongoals", "What should we explicitly avoid building in v1?"),
            ClarificationQuestion("q_constraints", "Any budget, compliance, or platform constraints?"),
        ]

        if has_mobile:
            questions.append(
                ClarificationQuestion("q_mobile_platforms", "Which mobile platforms and OS versions are required?")
            )
        if has_web:
            questions.append(
                ClarificationQuestion("q_web_stack", "Do you have web stack/design-system preferences?")
            )
        if has_ai:
            questions.append(
                ClarificationQuestion("q_ai_policy", "What safety/privacy constraints should AI behavior follow?")
            )

        questions.append(
            ClarificationQuestion("q_timeline", "What is the target delivery timeline and rollout milestone?")
        )
        return questions

    def initialize_state(self, raw_description: str) -> RequirementsState:
        questions = self.generate_questions(raw_description)
        return RequirementsState(raw_description=str(raw_description or "").strip(), questions=questions, answered_count=0)

    def record_answer(self, state: RequirementsState, answer_text: str) -> RequirementsState:
        normalized_answer = str(answer_text or "").strip()
        if not normalized_answer:
            return state

        for item in state.questions:
            if item.answer is None:
                item.answer = normalized_answer
                break

        state.answered_count = sum(1 for item in state.questions if bool(str(item.answer or "").strip()))
        return state

    def requirements_complete(self, state: RequirementsState) -> bool:
        answered = sum(1 for item in state.questions if bool(str(item.answer or "").strip()))
        return answered >= min(self.min_answered, len(state.questions))

    def next_unanswered_question(self, state: RequirementsState) -> Optional[ClarificationQuestion]:
        for item in state.questions:
            if not str(item.answer or "").strip():
                return item
        return None
