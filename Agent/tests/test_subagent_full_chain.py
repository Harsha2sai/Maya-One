import asyncio

import pytest

from core.agents.contracts import AgentHandoffRequest
from core.agents.handoff_manager import HandoffManager
from core.agents.registry import AgentRegistry


class _FakeBus:
    def __init__(self):
        self.events = []

    async def publish(self, channel, payload, **kwargs):
        self.events.append((channel, payload, kwargs))
        return {"ok": True}


class _FakePersistence:
    def __init__(self):
        self.checkpoints = []
        self.terminals = []

    async def save_checkpoint(self, task_id, step_id, payload, checkpoint_id=None, ts=None):
        self.checkpoints.append(
            {
                "task_id": task_id,
                "step_id": step_id,
                "payload": payload,
            }
        )
        return checkpoint_id or "chk_test"

    async def mark_terminal(self, task_id, status, reason):
        self.terminals.append(
            {
                "task_id": task_id,
                "status": status,
                "reason": reason,
            }
        )
        return True


def _request(*, target_agent: str, task_id: str, worktree_path: str, metadata: dict) -> AgentHandoffRequest:
    return AgentHandoffRequest(
        handoff_id=f"handoff-{target_agent}-{task_id}",
        trace_id=f"trace-{task_id}",
        conversation_id=f"conversation-{task_id}",
        task_id=task_id,
        parent_agent="maya",
        active_agent="maya",
        target_agent=target_agent,
        intent="planning",
        user_text="build a calculator",
        context_slice="full chain integration test",
        execution_mode="planning",
        delegation_depth=0,
        max_depth=1,
        handoff_reason="test full chain",
        metadata={
            "user_id": "u1",
            "worktree_path": worktree_path,
            **metadata,
        },
    )


async def _wait_for_completed(manager: HandoffManager, agent_id: str, *, timeout: float = 1.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        status = manager.subagent_manager.get_status(agent_id)
        if status["status"] == "completed":
            return status
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"subagent did not complete in time: {agent_id}")
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_architect_coder_reviewer_chain(tmp_path, monkeypatch):
    bus = _FakeBus()
    persistence = _FakePersistence()
    monkeypatch.setattr(HandoffManager, "_build_message_bus", staticmethod(lambda: bus))
    monkeypatch.setattr(HandoffManager, "_build_task_persistence", staticmethod(lambda: persistence))

    manager = HandoffManager(AgentRegistry())

    architect_result = await manager.delegate(
        _request(
            target_agent="subagent_architect",
            task_id="task-full-chain",
            worktree_path=str(tmp_path),
            metadata={
                "design_doc_path": "docs/calculator_design.md",
                "design_context": {
                    "scope": "calculator feature",
                    "constraints": ["preserve isolated runtime semantics"],
                    "assumptions": ["single delegated worktree"],
                    "target_files": ["src/calculator.py"],
                },
                "implementation_steps": [
                    {
                        "step_id": "step_1",
                        "title": "create calculator module",
                        "description": "write the calculator implementation",
                        "file_writes": [
                            {
                                "path": "src/calculator.py",
                                "content": (
                                    "def add(a, b):\n"
                                    "    print('debug calculator')\n"
                                    "    return a + b\n"
                                ),
                            }
                        ],
                    }
                ],
            },
        )
    )

    assert architect_result.status == "completed"
    architect_id = architect_result.structured_payload["subagent"]["agent_id"]
    architect_status = await _wait_for_completed(manager, architect_id)
    coder_id = architect_status["metadata"]["result"]["delegated_subagent"]["agent_id"]
    coder_status = await _wait_for_completed(manager, coder_id)

    reviewer_result = await manager.delegate(
        _request(
            target_agent="subagent_reviewer",
            task_id="task-full-chain-review",
            worktree_path=str(tmp_path),
            metadata={
                "file_paths": coder_status["metadata"]["result"]["changed_files"],
            },
        )
    )

    assert reviewer_result.status == "completed"
    reviewer_id = reviewer_result.structured_payload["subagent"]["agent_id"]
    reviewer_status = await _wait_for_completed(manager, reviewer_id)

    assert architect_status["worktree_path"] == str(tmp_path)
    assert coder_status["worktree_path"] == str(tmp_path)
    assert reviewer_status["worktree_path"] == str(tmp_path)
    assert (tmp_path / "docs" / "calculator_design.md").exists()
    assert (tmp_path / "src" / "calculator.py").exists()

    review_comments = reviewer_status["metadata"]["result"]["comments"]
    assert any(comment["category"] == "debug_artifact" for comment in review_comments)

    checkpoint_events = {
        (item["step_id"], item["payload"]["event"])
        for item in persistence.checkpoints
    }
    assert ("subagent_architect", "subagent_architect_completed") in checkpoint_events
    assert ("subagent_coder", "subagent_coder_completed") in checkpoint_events
    assert ("subagent_reviewer", "subagent_reviewer_completed") in checkpoint_events

    terminal_statuses = [item["status"] for item in persistence.terminals]
    assert terminal_statuses.count("COMPLETED") >= 3
    assert any(event[1]["agent"] == "subagent_architect" and event[1]["status"] == "completed" for event in bus.events)
    assert any(event[1]["agent"] == "subagent_coder" and event[1]["status"] == "completed" for event in bus.events)
    assert any(event[1]["agent"] == "subagent_reviewer" and event[1]["status"] == "completed" for event in bus.events)

    assert manager._is_subagent_circuit_open("subagent_architect") is False
    assert manager._is_subagent_circuit_open("subagent_coder") is False
    assert manager._is_subagent_circuit_open("subagent_reviewer") is False
