"""Project-mode manager for clarification conversations and PRD generation."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from core.memory.memdir import SessionStore

from .clarification import ClarificationQuestion, RequirementsGatherer, RequirementsState
from .prd_generator import PRD, PRDGenerator


class ProjectManager:
    """Orchestrates conversation lifecycle and persists state in SessionStore."""

    def __init__(
        self,
        *,
        session_store: Optional[SessionStore] = None,
        gatherer: Optional[RequirementsGatherer] = None,
        prd_generator: Optional[PRDGenerator] = None,
    ) -> None:
        self._session_store = session_store or self._resolve_session_store()
        self._gatherer = gatherer or RequirementsGatherer()
        self._prd_generator = prd_generator or PRDGenerator()

    def start_conversation(self, user_id: str) -> Dict[str, Any]:
        normalized_user = str(user_id or "").strip()
        if not normalized_user:
            raise ValueError("user_id is required")

        session_id = f"project_{uuid.uuid4().hex[:16]}"
        state = {
            "session_id": session_id,
            "user_id": normalized_user,
            "phase": "awaiting_description",
            "requirements": None,
            "prd": None,
        }
        self._save_state(session_id, state)
        return {
            "session_id": session_id,
            "phase": "awaiting_description",
            "message": "Describe the project idea to begin requirements clarification.",
        }

    def on_user_input(self, session_id: str, text: str) -> Dict[str, Any]:
        state = self._load_state(session_id)
        user_text = str(text or "").strip()
        if not user_text:
            raise ValueError("text is required")

        phase = str(state.get("phase") or "awaiting_description")
        if phase == "awaiting_description":
            requirements = self._gatherer.initialize_state(user_text)
            state["requirements"] = requirements.to_dict()
            state["phase"] = "clarifying"
            self._save_state(session_id, state)

            next_question = self._gatherer.next_unanswered_question(requirements)
            return {
                "session_id": session_id,
                "phase": state["phase"],
                "requirements_complete": False,
                "next_question": next_question.to_dict() if next_question else None,
                "answered_count": requirements.answered_count,
            }

        requirements = self._hydrate_requirements(state)
        updated = self._gatherer.record_answer(requirements, user_text)
        complete = self._gatherer.requirements_complete(updated)

        if complete:
            state["phase"] = "ready_for_prd"
        state["requirements"] = updated.to_dict()
        self._save_state(session_id, state)

        next_question = self._gatherer.next_unanswered_question(updated)
        return {
            "session_id": session_id,
            "phase": state["phase"],
            "requirements_complete": complete,
            "answered_count": updated.answered_count,
            "next_question": next_question.to_dict() if next_question else None,
        }

    def generate_prd(self, session_id: str) -> PRD:
        state = self._load_state(session_id)
        requirements = self._hydrate_requirements(state)

        if not self._gatherer.requirements_complete(requirements):
            raise ValueError("requirements are incomplete")

        prd = self._prd_generator.generate(requirements)
        state["phase"] = "prd_generated"
        state["prd"] = prd.to_dict()
        self._save_state(session_id, state)
        return prd

    def _load_state(self, session_id: str) -> Dict[str, Any]:
        payload = self._session_store.load(session_id)
        if payload is None:
            raise KeyError(f"session_not_found:{session_id}")

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError(f"invalid_session_payload:{session_id}")
        return dict(data)

    def _save_state(self, session_id: str, state: Dict[str, Any]) -> None:
        self._session_store.save(session_id, state)

    def _hydrate_requirements(self, state: Dict[str, Any]) -> RequirementsState:
        raw = dict(state.get("requirements") or {})
        questions = []
        for item in list(raw.get("questions") or []):
            if isinstance(item, dict):
                questions.append(
                    ClarificationQuestion(
                        question_id=str(item.get("question_id") or ""),
                        text=str(item.get("text") or ""),
                        answer=item.get("answer"),
                    )
                )

        requirements = RequirementsState(
            raw_description=str(raw.get("raw_description") or ""),
            questions=questions,
            answered_count=int(raw.get("answered_count") or 0),
        )
        requirements.answered_count = sum(
            1 for item in requirements.questions if bool(str(item.answer or "").strip())
        )
        return requirements

    @staticmethod
    def _resolve_session_store() -> SessionStore:
        try:
            from core.runtime.global_agent import GlobalAgentContainer

            store = GlobalAgentContainer.get_session_store()
            if store is not None:
                return store
        except Exception:
            pass
        return SessionStore()
