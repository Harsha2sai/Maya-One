from pathlib import Path

import pytest

from core.agents.subagent_coder import CodingTask, SubAgentCoder
from core.agents.subagent_reviewer import (
    ReviewTask,
    ReviewType,
    SubAgentReviewer,
    SubAgentReviewerError,
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


@pytest.mark.asyncio
async def test_subagent_reviewer_reviews_files_and_checkpoints(tmp_path):
    bus = _FakeBus()
    persistence = _FakePersistence()
    reviewer = SubAgentReviewer(message_bus=bus, persistence=persistence)

    review_file = tmp_path / "src" / "module.py"
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_text("print('debug')\n# TODO: tighten behavior\n", encoding="utf-8")

    task = ReviewTask(
        task_id="task-review-1",
        trace_id="trace-review-1",
        parent_handoff_id="handoff-review-1",
        delegation_chain_id="chain-review-1",
        file_paths=["src/module.py"],
    )

    result = await reviewer.execute(task, _worktree(tmp_path))

    assert result.success is True
    assert len(result.comments) == 2
    assert {comment.category for comment in result.comments} == {"debug_artifact", "todo_marker"}
    assert any(c["payload"]["event"] == "subagent_reviewer_completed" for c in persistence.checkpoints)
    assert any(event[1]["status"] == "completed" for event in bus.events)


@pytest.mark.asyncio
async def test_subagent_reviewer_analyzes_diff_between_refs(tmp_path):
    commands = []

    def _runner(command, _cwd):
        commands.append(command)
        if "--numstat" in command:
            return 0, "3\t1\tsrc/module.py\n", ""
        return 0, "@@ -1 +1 @@\n+print('debug')\n", ""

    reviewer = SubAgentReviewer(command_runner=_runner)
    task = ReviewTask(
        task_id="task-review-2",
        trace_id="trace-review-2",
        parent_handoff_id="handoff-review-2",
        delegation_chain_id="chain-review-2",
        file_paths=["src/module.py"],
        review_type=ReviewType.DIFF,
        base_ref="origin/main",
        head_ref="HEAD",
    )

    review_file = tmp_path / "src" / "module.py"
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_text("print('debug')\n", encoding="utf-8")

    result = await reviewer.execute(task, _worktree(tmp_path))

    assert result.success is True
    assert result.analysis is not None
    assert result.analysis.base_ref == "origin/main"
    assert result.analysis.stats["src/module.py"]["additions"] == 3
    assert any(comment.category == "debug_artifact" for comment in result.comments)
    assert commands[0][-2:] == ["origin/main", "HEAD"]


@pytest.mark.asyncio
async def test_depth_two_chain_coder_output_can_be_reviewed(tmp_path):
    bus = _FakeBus()
    persistence = _FakePersistence()
    coder = SubAgentCoder(message_bus=bus, persistence=persistence)
    reviewer = SubAgentReviewer(message_bus=bus, persistence=persistence)

    coding_task = CodingTask(
        task_id="task-chain-1",
        trace_id="trace-chain-1",
        parent_handoff_id="handoff-chain-1",
        delegation_chain_id="chain-chain-1",
        file_writes=[
            {
                "path": "src/generated.py",
                "content": "def run():\n    print('debug')\n",
            }
        ],
    )
    coding_result = await coder.execute(coding_task, _worktree(tmp_path))

    review_task = ReviewTask(
        task_id="task-chain-1",
        trace_id="trace-chain-1",
        parent_handoff_id="handoff-chain-2",
        delegation_chain_id="chain-chain-1",
        file_paths=coding_result.changed_files,
    )
    review_result = await reviewer.execute(review_task, _worktree(tmp_path))

    assert coding_result.changed_files == ["src/generated.py"]
    assert review_result.success is True
    assert review_result.file_paths == ["src/generated.py"]
    assert any(comment.category == "debug_artifact" for comment in review_result.comments)


@pytest.mark.asyncio
async def test_subagent_reviewer_raises_when_review_target_missing(tmp_path):
    reviewer = SubAgentReviewer()
    task = ReviewTask(
        task_id="task-review-3",
        trace_id="trace-review-3",
        parent_handoff_id="handoff-review-3",
        delegation_chain_id="chain-review-3",
        file_paths=["src/missing.py"],
    )

    with pytest.raises(SubAgentReviewerError) as exc:
        await reviewer.execute(task, _worktree(tmp_path))

    assert exc.value.code == "review_file_missing"
