from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkItem:
    prompt: str
    expected_route: str
    success_criterion: str
    actual_response: str = ""
    actual_route: str = ""
    passed: bool = False
    latency_ms: float = 0.0
    notes: str = ""


@dataclass
class EvalResult:
    items: List[BenchmarkItem]
    score: float = 0.0
    total: int = 0
    passed: int = 0
    failed_items: List[str] = field(default_factory=list)


BENCHMARK_TASKS: List[Tuple[str, str, str]] = [
    ("What is your name?", "chat", "maya"),
    ("What time is it?", "chat", "time"),
    ("Set a reminder to drink water in 10 minutes", "scheduling", "reminder"),
    ("Play some jazz music", "media", "music"),
    ("Search for recent AI research papers", "research", "research"),
    ("Create a task to review my code", "task", "task"),
    ("Who is the prime minister of Japan?", "research", "japan"),
    ("Pause the music", "media", "pause"),
    ("Remind me to call John tomorrow at 9am", "scheduling", "reminder"),
    ("What can you do?", "chat", "help"),
]


class MayaEvaluator:
    """
    ACEBench-style benchmark runner for routing/output quality checks.
    """

    def __init__(self, orchestrator: Any):
        self.orchestrator = orchestrator

    async def run(
        self,
        tasks: Optional[List[Tuple[str, str, str]]] = None,
        timeout_per_task: float = 30.0,
    ) -> EvalResult:
        task_list = tasks or BENCHMARK_TASKS
        items: List[BenchmarkItem] = []

        for prompt, expected_route, criterion in task_list:
            item = BenchmarkItem(
                prompt=prompt,
                expected_route=expected_route,
                success_criterion=criterion,
            )
            start = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    self.orchestrator.handle_message(message=prompt, user_id="eval_user"),
                    timeout=timeout_per_task,
                )
                item.latency_ms = (time.monotonic() - start) * 1000.0
                item.actual_response = self._extract_text(response)
                item.actual_route = self._extract_route(response, expected_route)
                item.passed = criterion.lower() in item.actual_response.lower()
                if not item.passed:
                    item.notes = f"criterion '{criterion}' not in response"
            except asyncio.TimeoutError:
                item.latency_ms = timeout_per_task * 1000.0
                item.notes = "timeout"
            except Exception as exc:
                item.latency_ms = (time.monotonic() - start) * 1000.0
                item.notes = f"error: {exc}"

            items.append(item)
            logger.info(
                "eval_item prompt='%s...' passed=%s latency=%.0fms route=%s",
                prompt[:40],
                item.passed,
                item.latency_ms,
                item.actual_route or "unknown",
            )

        passed = sum(1 for item in items if item.passed)
        failed = [item.prompt[:50] for item in items if not item.passed]
        result = EvalResult(
            items=items,
            score=round((passed / len(items)), 3) if items else 0.0,
            total=len(items),
            passed=passed,
            failed_items=failed,
        )
        logger.info("eval_complete score=%s passed=%s/%s", result.score, passed, len(items))
        return result

    @staticmethod
    def _extract_text(response: Any) -> str:
        if response is None:
            return ""
        if hasattr(response, "display_text"):
            return str(getattr(response, "display_text", "") or "")
        return str(response)

    @staticmethod
    def _extract_route(response: Any, default_route: str) -> str:
        try:
            structured = getattr(response, "structured_data", None) or {}
            route = structured.get("_routing_mode_type")
            if route:
                return str(route)
        except Exception:
            pass
        return default_route

