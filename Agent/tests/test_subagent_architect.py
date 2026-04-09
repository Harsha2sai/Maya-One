import asyncio
from pathlib import Path

import pytest

from core.agents.contracts import AgentHandoffRequest
from core.agents.handoff_manager import HandoffManager
from core.agents.registry import AgentRegistry
from core.agents.subagent_architect import (
    ArchitectTask,
    DesignContext,
    SubAgentArchitect,
    SubAgentArchitectError,
)
from core.agents.worktree_manager import WorktreeContext


class _FakeBus:
    def __init__(self):
        self.events = []

    async def publish(self, channel, payload, **kwargs):
        self.events.append((channel, payload, kwargs))
        return {"ok": True}


class _FakePersistence:
    def __init__(self):
        self.checkpoints = []

    async def save_checkpoint(self, task_id, step_id, payload, checkpoint_id=None, ts=None):
        self.checkpoints.append(
            {
                "task_id": task_id,
                "step_id": step_id,
                "payload": payload,
            }
        )
        return checkpoint_id or "chk_test"


class _FakeSubAgentManager:
    def __init__(self):
        self.calls = []

    async def spawn(self, agent_type, task_context, worktree_path=None):
        self.calls.append((agent_type, task_context, worktree_path))
        return {
            "agent_id": "subag_coder_1",
            "agent_type": agent_type,
            "status": "running",
        }


def _worktree(tmp_path: Path) -> WorktreeContext:
    return WorktreeContext(
        worktree_id="wt_1",
        task_id="task-1",
        path=str(tmp_path),
        branch="subagent/task-1/wt_1",
        base_branch="HEAD",
        status="running",
        created_at=1.0,
        updated_at=1.0,
    )


def _architect_task(**overrides) -> ArchitectTask:
    payload = {
        "task_id": "task-architect-1",
        "trace_id": "trace-architect-1",
        "parent_handoff_id": "handoff-architect-1",
        "delegation_chain_id": "chain-architect-1",
        "requirements": "Design a delegated implementation for generated code",
        "design_context": DesignContext(
            scope="delegated code generation",
            constraints=["preserve runtime compatibility"],
            assumptions=["single worktree execution"],
            target_files=["src/generated.py"],
        ),
        "implementation_steps": [
            {
                "step_id": "step_1",
                "title": "generate code",
                "description": "create the generated module",
                "file_writes": [
                    {
                        "path": "src/generated.py",
                        "content": "def run():\n    return 'ok'\n",
                    }
                ],
            }
        ],
        "design_doc_path": "docs/architecture.md",
        "auto_delegate": True,
    }
    payload.update(overrides)
    return ArchitectTask(**payload)


@pytest.mark.asyncio
async def test_subagent_architect_creates_design_plan_and_checkpoints(tmp_path):
    bus = _FakeBus()
    persistence = _FakePersistence()
    subagent_manager = _FakeSubAgentManager()
    architect = SubAgentArchitect(
        subagent_manager=subagent_manager,
        message_bus=bus,
        persistence=persistence,
    )

    result = await architect.execute(_architect_task(), _worktree(tmp_path))

    assert result.success is True
    assert result.design.design_doc_path == "docs/architecture.md"
    assert result.plan.steps[0].step_id == "step_1"
    assert result.delegated_subagent["agent_id"] == "subag_coder_1"
    assert (tmp_path / "docs" / "architecture.md").exists()
    assert any(c["payload"]["event"] == "subagent_architect_completed" for c in persistence.checkpoints)
    assert any(event[1]["status"] == "completed" for event in bus.events)


@pytest.mark.asyncio
async def test_subagent_architect_requires_implementation_steps(tmp_path):
    architect = SubAgentArchitect(subagent_manager=_FakeSubAgentManager())

    with pytest.raises(SubAgentArchitectError) as exc:
        await architect.execute(
            _architect_task(implementation_steps=[]),
            _worktree(tmp_path),
        )

    assert exc.value.code == "implementation_steps_required"


@pytest.mark.asyncio
async def test_subagent_architect_runtime_delegates_to_coder_via_handoff_manager(tmp_path):
    manager = HandoffManager(AgentRegistry())
    result = await manager.delegate(
        AgentHandoffRequest(
            handoff_id="handoff-architect-runtime",
            trace_id="trace-architect-runtime",
            conversation_id="conversation-architect-runtime",
            task_id="task-architect-runtime",
            parent_agent="maya",
            active_agent="maya",
            target_agent="subagent_architect",
            intent="planning",
            user_text="Design a generated module and delegate the implementation",
            context_slice="Architect planning flow",
            execution_mode="planning",
            delegation_depth=0,
            max_depth=1,
            handoff_reason="test architect runtime",
            metadata={
                "worktree_path": str(tmp_path),
                "design_doc_path": "docs/architecture.md",
                "design_context": {
                    "scope": "generated module",
                    "constraints": ["keep isolated worktree semantics"],
                    "target_files": ["src/generated.py"],
                },
                "implementation_steps": [
                    {
                        "step_id": "step_1",
                        "title": "generate module",
                        "description": "write the generated module",
                        "file_writes": [
                            {
                                "path": "src/generated.py",
                                "content": "def run():\n    print('architect')\n",
                            }
                        ],
                    }
                ],
            },
        )
    )

    assert result.status == "completed"
    architect_id = result.structured_payload["subagent"]["agent_id"]
    await asyncio.sleep(0.1)
    architect_status = manager.subagent_manager.get_status(architect_id)
    delegated = architect_status["metadata"]["result"]["delegated_subagent"]
    coder_id = delegated["agent_id"]
    coder_status = manager.subagent_manager.get_status(coder_id)

    assert architect_status["status"] == "completed"
    assert coder_status["status"] == "completed"
    assert (tmp_path / "docs" / "architecture.md").exists()
    assert (tmp_path / "src" / "generated.py").exists()
