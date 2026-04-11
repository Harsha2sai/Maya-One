from __future__ import annotations

import asyncio
import json

import pytest

from core.rl.outcome_logger import OutcomeLogger, TaskOutcome


@pytest.fixture
def store(tmp_path):
    return OutcomeLogger(store_path=tmp_path)


def _make_outcome(**kwargs) -> TaskOutcome:
    defaults = dict(
        task_id="task-001",
        agent_type="coder",
        prompt="Write hello world",
        response="def hello(): print('hello')",
        success=True,
        route="task",
        latency_ms=420.0,
    )
    defaults.update(kwargs)
    return TaskOutcome(**defaults)


@pytest.mark.asyncio
async def test_log_writes_jsonl(store, tmp_path):
    await store.log(_make_outcome())
    files = list(tmp_path.glob("outcomes_*.jsonl"))
    assert len(files) == 1
    records = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines() if line]
    assert len(records) == 1
    assert records[0]["task_id"] == "task-001"


@pytest.mark.asyncio
async def test_log_multiple_records(store, tmp_path):
    for idx in range(5):
        await store.log(_make_outcome(task_id=f"task-{idx:03d}"))
    files = list(tmp_path.glob("outcomes_*.jsonl"))
    records = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines() if line]
    assert len(records) == 5


@pytest.mark.asyncio
async def test_rate_updates_record(store, tmp_path):
    await store.log(_make_outcome(task_id="rate-me"))
    updated = await store.rate("rate-me", 5)
    assert updated is True
    files = list(tmp_path.glob("outcomes_*.jsonl"))
    records = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines() if line]
    assert records[0]["user_rating"] == 5


@pytest.mark.asyncio
async def test_rate_missing_task_returns_false(store):
    result = await store.rate("nonexistent", 4)
    assert result is False


@pytest.mark.asyncio
async def test_rate_invalid_rating_raises(store):
    await store.log(_make_outcome())
    with pytest.raises(ValueError):
        await store.rate("task-001", 6)


def test_iter_outcomes_filters_success(store):
    async def _setup():
        await store.log(_make_outcome(task_id="s1", success=True))
        await store.log(_make_outcome(task_id="f1", success=False))

    asyncio.run(_setup())
    results = list(store.iter_outcomes(success_only=True))
    assert len(results) == 1
    assert all(record["success"] for record in results)


def test_stats_structure(store):
    asyncio.run(store.log(_make_outcome()))
    stats = store.stats(days=1)
    assert "total" in stats
    assert "success_rate" in stats
    assert "by_route" in stats
    assert stats["total"] == 1
    assert stats["success_rate"] == 1.0

