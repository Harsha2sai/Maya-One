import pytest

from core.agents.project.clarification import RequirementsGatherer, RequirementsState
from core.agents.project.prd_generator import PRDGenerator
from core.agents.project.project_manager import ProjectManager
from core.memory.memdir import SessionStore
from core.runtime.global_agent import GlobalAgentContainer


def _new_manager(tmp_path, *, min_answered=4):
    store = SessionStore(base_dir=str(tmp_path))
    gatherer = RequirementsGatherer(min_answered=min_answered)
    manager = ProjectManager(session_store=store, gatherer=gatherer)
    return manager, store


def test_requirements_gatherer_generates_default_questions_for_empty_description():
    gatherer = RequirementsGatherer()
    questions = gatherer.generate_questions("")

    assert len(questions) >= 5
    ids = {q.question_id for q in questions}
    assert {"q_goal", "q_users", "q_scope", "q_constraints", "q_timeline"}.issubset(ids)


def test_requirements_gatherer_generates_contextual_questions_for_mobile_web_ai():
    gatherer = RequirementsGatherer()
    questions = gatherer.generate_questions("Build a mobile web AI assistant app")
    ids = {q.question_id for q in questions}

    assert "q_mobile_platforms" in ids
    assert "q_web_stack" in ids
    assert "q_ai_policy" in ids


def test_initialize_state_sets_answered_count_zero():
    gatherer = RequirementsGatherer()
    state = gatherer.initialize_state("Build a task planner")

    assert isinstance(state, RequirementsState)
    assert state.answered_count == 0
    assert len(state.questions) >= 5


def test_record_answer_updates_first_unanswered_and_count():
    gatherer = RequirementsGatherer()
    state = gatherer.initialize_state("Build project")

    gatherer.record_answer(state, "Outcome A")
    gatherer.record_answer(state, "User B")

    assert state.answered_count == 2
    assert state.questions[0].answer == "Outcome A"
    assert state.questions[1].answer == "User B"


def test_record_answer_ignores_blank_input():
    gatherer = RequirementsGatherer()
    state = gatherer.initialize_state("Build project")

    gatherer.record_answer(state, "   ")
    assert state.answered_count == 0


def test_requirements_complete_respects_threshold():
    gatherer = RequirementsGatherer(min_answered=2)
    state = gatherer.initialize_state("Build project")

    assert gatherer.requirements_complete(state) is False
    gatherer.record_answer(state, "A1")
    assert gatherer.requirements_complete(state) is False
    gatherer.record_answer(state, "A2")
    assert gatherer.requirements_complete(state) is True


def test_next_unanswered_question_returns_none_when_all_answered():
    gatherer = RequirementsGatherer(min_answered=2)
    state = gatherer.initialize_state("Build project")

    for _ in state.questions:
        gatherer.record_answer(state, "filled")

    assert gatherer.next_unanswered_question(state) is None


def test_prd_generator_populates_required_fields_and_open_questions():
    gatherer = RequirementsGatherer()
    state = gatherer.initialize_state("Build a website for clinic appointments")
    gatherer.record_answer(state, "Allow booking quickly")
    gatherer.record_answer(state, "Patients and admins")
    gatherer.record_answer(state, "Booking + reminders")

    prd = PRDGenerator().generate(state)

    assert prd.title.startswith("PRD:")
    assert "clinic appointments" in prd.overview
    assert len(prd.goals) >= 1
    assert isinstance(prd.technical_requirements, list)
    assert len(prd.open_questions) >= 1


def test_project_manager_start_conversation_persists_state(tmp_path):
    manager, store = _new_manager(tmp_path)
    started = manager.start_conversation("user-1")

    persisted = store.load(started["session_id"])
    assert started["phase"] == "awaiting_description"
    assert persisted["data"]["user_id"] == "user-1"


def test_project_manager_start_conversation_requires_user_id(tmp_path):
    manager, _ = _new_manager(tmp_path)

    with pytest.raises(ValueError):
        manager.start_conversation("")


def test_on_user_input_initial_description_transitions_to_clarifying(tmp_path):
    manager, _ = _new_manager(tmp_path)
    started = manager.start_conversation("user-1")

    response = manager.on_user_input(started["session_id"], "Build a mobile AI todo app")

    assert response["phase"] == "clarifying"
    assert response["requirements_complete"] is False
    assert response["next_question"] is not None


def test_on_user_input_progression_reaches_ready_for_prd(tmp_path):
    manager, _ = _new_manager(tmp_path, min_answered=3)
    started = manager.start_conversation("user-1")
    manager.on_user_input(started["session_id"], "Build an analytics dashboard")

    r1 = manager.on_user_input(started["session_id"], "Goal 1")
    r2 = manager.on_user_input(started["session_id"], "Users 1")
    r3 = manager.on_user_input(started["session_id"], "Scope 1")

    assert r1["requirements_complete"] is False
    assert r2["requirements_complete"] is False
    assert r3["requirements_complete"] is True
    assert r3["phase"] == "ready_for_prd"


def test_on_user_input_requires_non_empty_text(tmp_path):
    manager, _ = _new_manager(tmp_path)
    started = manager.start_conversation("user-1")

    with pytest.raises(ValueError):
        manager.on_user_input(started["session_id"], "")


def test_generate_prd_requires_completed_requirements(tmp_path):
    manager, _ = _new_manager(tmp_path)
    started = manager.start_conversation("user-1")
    manager.on_user_input(started["session_id"], "Build project")

    with pytest.raises(ValueError):
        manager.generate_prd(started["session_id"])


def test_generate_prd_success_and_persistence(tmp_path):
    manager, store = _new_manager(tmp_path, min_answered=2)
    started = manager.start_conversation("user-1")
    manager.on_user_input(started["session_id"], "Build project mode for PRDs")
    manager.on_user_input(started["session_id"], "Goal answer")
    manager.on_user_input(started["session_id"], "Users answer")

    prd = manager.generate_prd(started["session_id"])
    persisted = store.load(started["session_id"])

    assert prd.title.startswith("PRD:")
    assert len(prd.goals) >= 1
    assert persisted["data"]["phase"] == "prd_generated"
    assert "prd" in persisted["data"]


def test_on_user_input_missing_session_raises(tmp_path):
    manager, _ = _new_manager(tmp_path)

    with pytest.raises(KeyError):
        manager.on_user_input("missing-session", "hello")


def test_project_manager_state_persists_across_instances(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    manager1 = ProjectManager(session_store=store, gatherer=RequirementsGatherer(min_answered=2))
    started = manager1.start_conversation("user-1")
    manager1.on_user_input(started["session_id"], "Build a reporting service")
    manager1.on_user_input(started["session_id"], "Goal")

    manager2 = ProjectManager(session_store=store, gatherer=RequirementsGatherer(min_answered=2))
    response = manager2.on_user_input(started["session_id"], "User type")

    assert response["requirements_complete"] is True
    assert response["phase"] == "ready_for_prd"


def test_project_manager_uses_global_container_session_store_when_available(tmp_path):
    original = GlobalAgentContainer._session_store
    try:
        injected = SessionStore(base_dir=str(tmp_path))
        GlobalAgentContainer._session_store = injected

        manager = ProjectManager()
        started = manager.start_conversation("user-42")

        assert injected.load(started["session_id"]) is not None
    finally:
        GlobalAgentContainer._session_store = original


def test_prd_generator_title_truncates_long_descriptions():
    desc = "Build an end to end voice-first project requirements and delivery assistant for cross-functional teams"
    state = RequirementsGatherer().initialize_state(desc)
    prd = PRDGenerator().generate(state)

    assert prd.title.startswith("PRD:")
    assert prd.title.endswith("...")
