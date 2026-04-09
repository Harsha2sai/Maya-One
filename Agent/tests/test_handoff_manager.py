import asyncio
from types import SimpleNamespace

import pytest

from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult, HandoffSignal
from core.agents.handoff_manager import HandoffManager, HandoffValidationError, get_handoff_manager
from core.agents.registry import AgentRegistry


def _request(**overrides) -> AgentHandoffRequest:
    payload = {
        "handoff_id": "handoff-1",
        "trace_id": "trace-1",
        "conversation_id": "conversation-1",
        "task_id": None,
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "research",
        "intent": "research",
        "user_text": "who is the current prime minister of japan",
        "context_slice": "User asked a research question.",
        "execution_mode": "inline",
        "delegation_depth": 0,
        "max_depth": 1,
        "handoff_reason": "test",
        "metadata": {"user_id": "u1"},
    }
    payload.update(overrides)
    return AgentHandoffRequest(**payload)


@pytest.mark.asyncio
async def test_invalid_parent_is_blocked():
    manager = HandoffManager(AgentRegistry())
    result = await manager.delegate(_request(parent_agent="planner"))
    assert result.status == "failed"
    assert result.error_code == "HandoffValidationError"


def test_background_handoff_requires_task_id():
    manager = HandoffManager(AgentRegistry())
    with pytest.raises(HandoffValidationError):
        manager.validate_request(_request(execution_mode="background", task_id=None))


def test_signal_maps_to_target():
    manager = HandoffManager(AgentRegistry())
    signal = HandoffSignal(
        signal_name="transfer_to_planner",
        reason="planning required",
        execution_mode="planning",
        context_hint="plan it",
    )
    assert manager.consume_signal(signal) == "planner"


def test_get_handoff_manager_returns_fresh_instance():
    manager_one = get_handoff_manager(AgentRegistry())
    manager_two = get_handoff_manager(AgentRegistry())
    assert manager_one is not manager_two


@pytest.mark.asyncio
async def test_depth_guard_blocks_subagent_delegation():
    manager = HandoffManager(AgentRegistry())
    result = await manager.delegate(
        _request(
            parent_agent="research",
            active_agent="research",
            target_agent="planner",
            execution_mode="planning",
            task_id="task-1",
            delegation_depth=1,
        )
    )
    assert result.status == "failed"
    assert result.error_code == "HandoffValidationError"
    assert any(
        token in str(result.error_detail or "")
        for token in ("parent_agent must be maya", "delegation depth exceeded")
    )


@pytest.mark.asyncio
async def test_zero_confidence_handoff_is_logged_and_allowed(caplog):
    class _Registry:
        async def can_accept(self, request):
            return AgentCapabilityMatch(
                agent_name=request.target_agent,
                confidence=0.0,
                reason="rewritten_followup_keyword_sparse",
                hard_constraints_passed=True,
            )

        async def handle(self, request):
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=request.target_agent,
                status="completed",
                user_visible_text=None,
                voice_text=None,
                structured_payload={"ok": True},
                next_action="continue",
                error_code=None,
                error_detail=None,
            )

    manager = HandoffManager(_Registry())
    with caplog.at_level("INFO"):
        result = await manager.delegate(_request())

    assert result.status == "completed"
    assert "handoff_zero_confidence_allowed" in caplog.text


def test_subagent_signal_maps_to_target():
    manager = HandoffManager(AgentRegistry())
    signal = HandoffSignal(
        signal_name="transfer_to_subagent_reviewer",
        reason="needs code review",
        execution_mode="planning",
        context_hint="review the patch",
    )
    assert manager.consume_signal(signal) == "subagent_reviewer"


@pytest.mark.asyncio
async def test_subagent_target_routes_to_subagent_manager_spawn():
    class _SubagentManager:
        def __init__(self):
            self.calls = []

        async def spawn(self, agent_type, task_context, worktree_path=None):
            self.calls.append(("spawn", agent_type, task_context, worktree_path))
            return {
                "agent_id": "subag_1",
                "agent_type": agent_type,
                "status": "running",
                "task_context": task_context,
                "worktree_path": worktree_path,
            }

    class _Registry:
        async def can_accept(self, _request):
            raise AssertionError("registry should not be used for subagent targets")

        async def handle(self, _request):
            raise AssertionError("registry should not be used for subagent targets")

    subagent_manager = _SubagentManager()
    manager = HandoffManager(_Registry(), subagent_manager=subagent_manager)

    result = await manager.delegate(
        _request(
            target_agent="subagent_coder",
            execution_mode="planning",
            task_id="task-9",
            metadata={
                "user_id": "u1",
                "base_branch": "HEAD",
                "delegation_chain_id": "chain-explicit",
            },
        )
    )

    assert result.status == "completed"
    assert result.next_action == "background"
    assert result.structured_payload["runtime"] == "subagent_manager"
    assert subagent_manager.calls
    _, _, task_context, _ = subagent_manager.calls[0]
    assert task_context["parent_handoff_id"] == "handoff-1"
    assert task_context["delegation_chain_id"] == "chain-explicit"


@pytest.mark.asyncio
async def test_background_subagent_target_routes_to_spawn_background():
    class _SubagentManager:
        def __init__(self):
            self.calls = []

        async def spawn(self, agent_type, task_context, worktree_path=None):
            raise AssertionError("foreground spawn should not be used")

        async def spawn_background(self, agent_type, task_context, recoverable=True):
            self.calls.append(("spawn_background", agent_type, task_context, recoverable))
            return {
                "task_ref": "subag_bg_1",
                "agent_id": "subag_bg_1",
                "agent_type": agent_type,
                "status": "running",
                "recoverable": recoverable,
            }

    manager = HandoffManager(AgentRegistry(), subagent_manager=_SubagentManager())
    result = await manager.delegate(
        _request(
            target_agent="subagent_coder",
            execution_mode="background",
            task_id="task-bg-1",
            metadata={"user_id": "u1"},
        ),
        background=True,
        recoverable=True,
    )

    assert result.status == "completed"
    assert result.next_action == "background"
    assert result.structured_payload["background"] is True
    assert result.structured_payload["recoverable"] is True
    assert result.structured_payload["subagent"]["task_ref"] == "subag_bg_1"
    assert manager.subagent_manager.calls[0][0] == "spawn_background"
    assert manager.subagent_manager.calls[0][3] is True


@pytest.mark.asyncio
async def test_delegate_background_convenience_uses_background_path():
    class _SubagentManager:
        def __init__(self):
            self.calls = []

        async def spawn(self, agent_type, task_context, worktree_path=None):
            raise AssertionError("foreground spawn should not be used")

        async def spawn_background(self, agent_type, task_context, recoverable=True):
            self.calls.append((agent_type, task_context, recoverable))
            return {
                "task_ref": "subag_bg_2",
                "agent_id": "subag_bg_2",
                "agent_type": agent_type,
                "status": "running",
                "recoverable": recoverable,
            }

    subagent_manager = _SubagentManager()
    manager = HandoffManager(AgentRegistry(), subagent_manager=subagent_manager)
    result = await manager.delegate_background(
        _request(
            target_agent="subagent_architect",
            execution_mode="planning",
            task_id="task-bg-2",
            metadata={"user_id": "u1"},
        ),
        recoverable=False,
    )

    assert result.status == "completed"
    assert result.structured_payload["background"] is True
    assert result.structured_payload["recoverable"] is False
    assert result.structured_payload["subagent"]["agent_type"] == "subagent_architect"
    assert subagent_manager.calls[0][2] is False


@pytest.mark.asyncio
async def test_subagent_circuit_opens_after_repeated_failures():
    class _SubagentManager:
        async def spawn(self, agent_type, task_context, worktree_path=None):
            raise RuntimeError(f"spawn failed for {agent_type}")

    manager = HandoffManager(AgentRegistry(), subagent_manager=_SubagentManager())

    for _ in range(manager.MAX_SUBAGENT_FAILURES):
        result = await manager.delegate(_request(target_agent="subagent_architect"))
        assert result.status == "failed"
        assert result.error_code == "RuntimeError"

    blocked = await manager.delegate(_request(target_agent="subagent_architect"))
    assert blocked.status == "failed"
    assert blocked.error_code == "subagent_circuit_open"


@pytest.mark.asyncio
async def test_subagent_reviewer_runtime_completes_via_handoff_manager(tmp_path):
    review_file = tmp_path / "src" / "module.py"
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_text("print('debug')\n", encoding="utf-8")

    manager = HandoffManager(AgentRegistry())
    result = await manager.delegate(
        _request(
            target_agent="subagent_reviewer",
            execution_mode="planning",
            task_id="task-review-runtime",
            metadata={
                "user_id": "u1",
                "worktree_path": str(tmp_path),
                "file_paths": ["src/module.py"],
            },
        )
    )

    assert result.status == "completed"
    agent_id = result.structured_payload["subagent"]["agent_id"]
    await asyncio.sleep(0.05)
    status = manager.subagent_manager.get_status(agent_id)

    assert status["status"] == "completed"
    comments = status["metadata"]["result"]["comments"]
    assert any(comment["category"] == "debug_artifact" for comment in comments)
