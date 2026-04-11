from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.commands.handlers.rl import handle_rl
from core.rl.evaluator import BENCHMARK_TASKS, EvalResult, MayaEvaluator
from core.rl.outcome_logger import OutcomeLogger, TaskOutcome
from core.rl.training_export import TrainingExporter


@pytest.fixture
def orchestrator_mock():
    orchestrator = MagicMock()

    async def smart_response(*args, **kwargs):
        message = kwargs.get("message") if kwargs else args[0]
        lowered = str(message).lower()
        if "name" in lowered:
            return "I'm Maya, your AI assistant."
        if "time" in lowered:
            return "The current time is 3:00 PM."
        if "reminder" in lowered:
            return "Reminder set successfully."
        if "jazz" in lowered or "music" in lowered:
            return "Playing jazz music now."
        if "research" in lowered:
            return "Here are recent research findings..."
        if "task" in lowered:
            return "Task created successfully."
        if "japan" in lowered:
            return "The prime minister of Japan is Ishiba."
        if "pause" in lowered:
            return "Music paused."
        if "help" in lowered or "can you do" in lowered:
            return "I can help with many tasks."
        return "Done."

    orchestrator.handle_message = AsyncMock(side_effect=smart_response)
    return orchestrator


@pytest.fixture
def evaluator(orchestrator_mock):
    return MayaEvaluator(orchestrator=orchestrator_mock)


@pytest.mark.asyncio
async def test_eval_returns_result(evaluator):
    result = await evaluator.run()
    assert isinstance(result, EvalResult)
    assert result.total == len(BENCHMARK_TASKS)
    assert 0.0 <= result.score <= 1.0


@pytest.mark.asyncio
async def test_eval_passes_most_tasks(evaluator):
    result = await evaluator.run()
    assert result.score >= 0.75, f"Score {result.score} below threshold. Failed: {result.failed_items}"


@pytest.mark.asyncio
async def test_eval_handles_timeout(orchestrator_mock):
    async def slow(*args, **kwargs):
        del args, kwargs
        await asyncio.sleep(100)

    orchestrator_mock.handle_message = AsyncMock(side_effect=slow)
    evaluator = MayaEvaluator(orchestrator=orchestrator_mock)
    result = await evaluator.run(
        tasks=[("hello", "chat", "hello")],
        timeout_per_task=0.1,
    )
    assert result.items[0].passed is False
    assert "timeout" in result.items[0].notes


@pytest.mark.asyncio
async def test_eval_handles_exception(orchestrator_mock):
    orchestrator_mock.handle_message = AsyncMock(side_effect=RuntimeError("LLM down"))
    evaluator = MayaEvaluator(orchestrator=orchestrator_mock)
    result = await evaluator.run(tasks=[("hello", "chat", "hello")])
    assert result.items[0].passed is False
    assert "error:" in result.items[0].notes


def test_training_export(tmp_path: Path):
    store = OutcomeLogger(store_path=tmp_path / "outcomes")
    asyncio.run(
        store.log(
            TaskOutcome(
                task_id="t1",
                agent_type="coder",
                prompt="Write code",
                response="def f(): pass",
                success=True,
                route="task",
                latency_ms=300.0,
            )
        )
    )
    asyncio.run(
        store.log(
            TaskOutcome(
                task_id="t2",
                agent_type="coder",
                prompt="Bad task",
                response="",
                success=False,
                route="task",
                latency_ms=5000.0,
            )
        )
    )

    exporter = TrainingExporter(store)
    output = tmp_path / "train.jsonl"
    count = exporter.export(output_path=output, days=1, success_only=True)
    assert count == 1
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line]
    assert records[0]["reward"] == 1.0
    assert records[0]["prompt"] == "Write code"


def test_reward_computation(tmp_path: Path):
    exporter = TrainingExporter(OutcomeLogger(store_path=tmp_path / "outcomes"))
    assert exporter._compute_reward({"success": True, "user_rating": 5, "latency_ms": 100}) == 1.0
    assert exporter._compute_reward({"success": True, "user_rating": 1, "latency_ms": 100}) == 1.0
    assert exporter._compute_reward({"success": False, "latency_ms": 100}) == 0.0
    assert exporter._compute_reward({"success": True, "latency_ms": 15_000}) == 0.9


@pytest.mark.asyncio
async def test_rl_handler_stats_rate_and_unknown(tmp_path: Path):
    logger = OutcomeLogger(store_path=tmp_path / "outcomes")
    await logger.log(
        TaskOutcome(
            task_id="abc123",
            agent_type="chat",
            prompt="hello",
            response="hi",
            success=True,
            route="chat",
            latency_ms=55.0,
        )
    )
    exporter = TrainingExporter(logger)
    evaluator = SimpleNamespace(run=AsyncMock(return_value=SimpleNamespace(
        passed=8,
        total=10,
        score=0.8,
        failed_items=["x"],
    )))

    context = {
        "outcome_logger": logger,
        "training_exporter": exporter,
        "evaluator": evaluator,
    }
    stats = await handle_rl("stats --days 1", context)
    assert "Outcome stats" in stats

    rated = await handle_rl("rate abc123 4", context)
    assert "Rating 4/5 saved" in rated

    unknown = await handle_rl("bogus", context)
    assert "Unknown subcommand" in unknown

