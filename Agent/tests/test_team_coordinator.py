import asyncio

import pytest

from core.agents.team import (
    ReviewFinding,
    ReviewReducer,
    ReviewSeverity,
    TeamCoordinator,
    TeamTask,
    TeamTaskStatus,
)


def test_register_and_list_agents_sorted():
    coordinator = TeamCoordinator()
    coordinator.register_agent("reviewer", lambda payload: payload)
    coordinator.register_agent("coder", lambda payload: payload)

    assert coordinator.list_agents() == ["coder", "reviewer"]


def test_register_agent_requires_name_and_callable():
    coordinator = TeamCoordinator()

    with pytest.raises(ValueError):
        coordinator.register_agent("", lambda payload: payload)

    with pytest.raises(TypeError):
        coordinator.register_agent("coder", "not-callable")


def test_unregister_agent_is_safe_for_missing():
    coordinator = TeamCoordinator()
    coordinator.register_agent("coder", lambda payload: payload)

    coordinator.unregister_agent("coder")
    coordinator.unregister_agent("coder")

    assert coordinator.list_agents() == []


@pytest.mark.asyncio
async def test_run_task_with_sync_handler_completes():
    coordinator = TeamCoordinator()
    coordinator.register_agent("coder", lambda payload: {"echo": payload["value"]})

    result = await coordinator.run_task(TeamTask(task_id="t1", agent_name="coder", payload={"value": 7}))

    assert result.status == TeamTaskStatus.COMPLETED
    assert result.result == {"echo": 7}
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_run_task_with_async_handler_completes():
    coordinator = TeamCoordinator()

    async def _handler(payload):
        await asyncio.sleep(0.01)
        return {"ok": payload.get("ok")}

    coordinator.register_agent("reviewer", _handler)
    result = await coordinator.run_task(TeamTask(task_id="t2", agent_name="reviewer", payload={"ok": True}))

    assert result.status == TeamTaskStatus.COMPLETED
    assert result.result == {"ok": True}


@pytest.mark.asyncio
async def test_run_task_unknown_agent_returns_failed():
    coordinator = TeamCoordinator()

    result = await coordinator.run_task(TeamTask(task_id="t3", agent_name="missing"))

    assert result.status == TeamTaskStatus.FAILED
    assert "unregistered_agent" in str(result.error)


@pytest.mark.asyncio
async def test_run_task_handler_exception_returns_failed():
    coordinator = TeamCoordinator()

    def _boom(_payload):
        raise RuntimeError("boom")

    coordinator.register_agent("coder", _boom)
    result = await coordinator.run_task(TeamTask(task_id="t4", agent_name="coder"))

    assert result.status == TeamTaskStatus.FAILED
    assert "boom" in str(result.error)


@pytest.mark.asyncio
async def test_run_task_timeout_returns_timeout():
    coordinator = TeamCoordinator()

    async def _slow(_payload):
        await asyncio.sleep(0.1)
        return {"ok": True}

    coordinator.register_agent("slow", _slow)
    result = await coordinator.run_task(TeamTask(task_id="t5", agent_name="slow", timeout_s=0.01))

    assert result.status == TeamTaskStatus.TIMEOUT
    assert result.error == "task_timeout"


@pytest.mark.asyncio
async def test_run_batch_returns_execution_for_each_task():
    coordinator = TeamCoordinator(max_parallel=2)
    coordinator.register_agent("coder", lambda payload: {"id": payload["id"]})

    tasks = [TeamTask(task_id=f"t{i}", agent_name="coder", payload={"id": i}) for i in range(5)]
    results = await coordinator.run_batch(tasks)

    assert len(results) == 5
    assert all(item.status == TeamTaskStatus.COMPLETED for item in results)


@pytest.mark.asyncio
async def test_run_batch_respects_max_parallel_limit():
    coordinator = TeamCoordinator(max_parallel=2)
    active = 0
    max_seen = 0

    async def _handler(_payload):
        nonlocal active, max_seen
        active += 1
        max_seen = max(max_seen, active)
        await asyncio.sleep(0.02)
        active -= 1
        return {"ok": True}

    coordinator.register_agent("worker", _handler)
    tasks = [TeamTask(task_id=f"t{i}", agent_name="worker") for i in range(8)]
    await coordinator.run_batch(tasks)

    assert max_seen <= 2
    assert max_seen >= 1


@pytest.mark.asyncio
async def test_run_batch_fail_fast_marks_waiting_tasks_cancelled():
    coordinator = TeamCoordinator(max_parallel=1)

    async def _handler(payload):
        if payload.get("fail"):
            raise RuntimeError("stop")
        await asyncio.sleep(0.05)
        return {"ok": True}

    coordinator.register_agent("worker", _handler)
    tasks = [
        TeamTask(task_id="t1", agent_name="worker", payload={"fail": True}),
        TeamTask(task_id="t2", agent_name="worker", payload={"fail": False}),
        TeamTask(task_id="t3", agent_name="worker", payload={"fail": False}),
    ]

    results = await coordinator.run_batch(tasks, fail_fast=True)

    assert results[0].status == TeamTaskStatus.FAILED
    assert any(item.status == TeamTaskStatus.CANCELLED for item in results[1:])


def test_reduce_first_success_picks_first_completed():
    coordinator = TeamCoordinator()
    executions = [
        TeamCoordinator.__dict__["run_task"],
    ]
    del executions

    from core.agents.team.coordinator import TeamExecution

    results = [
        TeamExecution(task_id="a", agent_name="coder", status=TeamTaskStatus.FAILED, error="x"),
        TeamExecution(task_id="b", agent_name="reviewer", status=TeamTaskStatus.COMPLETED, result={"ok": 1}),
        TeamExecution(task_id="c", agent_name="architect", status=TeamTaskStatus.COMPLETED, result={"ok": 2}),
    ]

    reduced = coordinator.reduce_results(results, strategy="first_success")

    assert reduced["success"] is True
    assert reduced["winner"]["task_id"] == "b"


def test_reduce_first_success_handles_no_success():
    from core.agents.team.coordinator import TeamExecution

    coordinator = TeamCoordinator()
    results = [
        TeamExecution(task_id="a", agent_name="coder", status=TeamTaskStatus.FAILED, error="x"),
    ]

    reduced = coordinator.reduce_results(results, strategy="first_success")

    assert reduced["success"] is False
    assert reduced["error"] == "no_successful_results"


def test_reduce_all_success_reports_failed_count():
    from core.agents.team.coordinator import TeamExecution

    coordinator = TeamCoordinator()
    results = [
        TeamExecution(task_id="a", agent_name="coder", status=TeamTaskStatus.COMPLETED, result={}),
        TeamExecution(task_id="b", agent_name="reviewer", status=TeamTaskStatus.TIMEOUT, error="timeout"),
    ]

    reduced = coordinator.reduce_results(results, strategy="all_success")

    assert reduced["success"] is False
    assert reduced["failed_count"] == 1


def test_reduce_merge_dict_combines_completed_dict_results():
    from core.agents.team.coordinator import TeamExecution

    coordinator = TeamCoordinator()
    results = [
        TeamExecution(task_id="a", agent_name="coder", status=TeamTaskStatus.COMPLETED, result={"x": 1}),
        TeamExecution(task_id="b", agent_name="reviewer", status=TeamTaskStatus.COMPLETED, result={"y": 2}),
        TeamExecution(task_id="c", agent_name="architect", status=TeamTaskStatus.FAILED, error="no"),
    ]

    reduced = coordinator.reduce_results(results, strategy="merge_dict")

    assert reduced["success"] is True
    assert reduced["merged"] == {"x": 1, "y": 2}


def test_reduce_review_uses_findings_and_blocks_on_error():
    from core.agents.team.coordinator import TeamExecution

    coordinator = TeamCoordinator()
    results = [
        TeamExecution(
            task_id="a",
            agent_name="reviewer",
            status=TeamTaskStatus.COMPLETED,
            result={
                "findings": [
                    {"severity": "warning", "message": "style"},
                    {"severity": "error", "message": "bug"},
                ]
            },
        ),
    ]

    reduced = coordinator.reduce_results(results, strategy="review")

    assert reduced["success"] is False
    assert reduced["review"]["should_block"] is True
    assert reduced["review"]["counts"]["error"] == 1


@pytest.mark.asyncio
async def test_coordinate_runs_batch_and_reduces():
    coordinator = TeamCoordinator(max_parallel=2)

    async def _coder(payload):
        await asyncio.sleep(0.01)
        return {"code": payload["v"]}

    coordinator.register_agent("coder", _coder)
    tasks = [
        TeamTask(task_id="t1", agent_name="coder", payload={"v": "a"}),
        TeamTask(task_id="t2", agent_name="coder", payload={"v": "b"}),
    ]

    reduced = await coordinator.coordinate(tasks, strategy="merge_dict")

    assert reduced["success"] is True
    assert reduced["merged"] == {"code": "b"}


def test_review_reducer_merge_and_summary_helpers():
    findings = ReviewReducer.merge_findings(
        [
            {"severity": "info", "message": "ok"},
            ReviewFinding(severity=ReviewSeverity.CRITICAL, message="bad"),
        ]
    )
    summary = ReviewReducer.summarize(findings)

    assert len(findings) == 2
    assert summary.total == 2
    assert summary.highest_severity == "critical"
    assert ReviewReducer.should_block(findings) is True
