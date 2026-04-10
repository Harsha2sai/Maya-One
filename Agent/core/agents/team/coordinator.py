import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from core.agents.subagent.manager import SubAgentManager
from core.messaging import MayaMsgHub

from .types import TeamMode, TeamResult, TeamTask, TeamTaskStatus, TeamExecution
from .review import ReviewFinding, ReviewReducer, ReviewSeverity

logger = logging.getLogger(__name__)

REVIEW_APPROVAL_SIGNALS = ("lgtm", "approved", "looks good", "no issues")
MAX_REVIEW_ITERATIONS = 3


class TeamCoordinator:
    """
    Spawns and coordinates teams of subagents (P30 API).
    Also exposes legacy task-dispatch API for backward compatibility.
    """

    def __init__(
        self,
        subagent_manager: Optional[SubAgentManager] = None,
        msg_hub: Optional[MayaMsgHub] = None,
        max_parallel: int = 5,
    ):
        # P30 API
        self.agents = subagent_manager
        self.hub = msg_hub
        # Legacy API
        self._handlers: Dict[str, Callable] = {}
        self._max_parallel = max_parallel

    # ── P30: Multi-agent team API ─────────────────────────────────────────────

    async def create_team(
        self,
        task: str,
        roles: List[str],
        mode: str = "parallel",
    ) -> TeamResult:
        team_mode = TeamMode(mode)
        logger.info("team_create mode=%s roles=%s", mode, roles)

        if team_mode == TeamMode.PARALLEL:
            return await self._parallel_run(task, roles)
        if team_mode == TeamMode.SEQUENTIAL:
            return await self._sequential_run(task, roles)
        if team_mode == TeamMode.REVIEW:
            return await self._review_loop(task)

        raise ValueError(f"Unknown team mode: {mode}")

    async def _parallel_run(self, task: str, roles: List[str]) -> TeamResult:
        spawn_tasks = [
            self.agents.spawn(agent_type=role, task=task, wait=True)
            for role in roles
        ]
        instances = await asyncio.gather(*spawn_tasks, return_exceptions=True)

        clean = []
        for i, result in enumerate(instances):
            if isinstance(result, Exception):
                logger.error("team_parallel_agent_failed role=%s: %s", roles[i], result)
            else:
                clean.append(result)

        return TeamResult(mode=TeamMode.PARALLEL, instances=clean)

    async def _sequential_run(self, task: str, roles: List[str]) -> TeamResult:
        instances = []
        current_task = task

        for role in roles:
            instance = await self.agents.spawn(
                agent_type=role, task=current_task, wait=True
            )
            instances.append(instance)

            if instance.result:
                current_task = (
                    f"Previous agent ({role}) produced:\n{instance.result}\n\n"
                    f"Original task: {task}\n\nContinue from here."
                )

        final = instances[-1].result if instances else None
        return TeamResult(
            mode=TeamMode.SEQUENTIAL,
            instances=instances,
            final_output=final,
        )

    async def _review_loop(
        self,
        task: str,
        max_iterations: int = MAX_REVIEW_ITERATIONS,
    ) -> TeamResult:
        iterations = []
        current_task = task
        approved = False

        for i in range(max_iterations):
            coder = await self.agents.spawn("coder", current_task, wait=True)
            reviewer = await self.agents.spawn(
                "reviewer",
                f"Review this code:\n\n{coder.result}\n\nOriginal task: {task}",
                wait=True,
            )

            iterations.append({
                "iteration": i + 1,
                "code": coder.result,
                "review": reviewer.result,
            })

            review_lower = (reviewer.result or "").lower()
            if any(sig in review_lower for sig in REVIEW_APPROVAL_SIGNALS):
                approved = True
                logger.info("team_review_approved iteration=%s", i + 1)
                break

            current_task = (
                f"{task}\n\n"
                f"Reviewer feedback (iteration {i + 1}):\n{reviewer.result}\n\n"
                "Please revise your implementation."
            )

        final = iterations[-1]["code"] if iterations else None
        return TeamResult(
            mode=TeamMode.REVIEW,
            iterations=iterations,
            final_output=final,
            approved=approved,
        )

    # ── Legacy task-dispatch API (pre-P30, backward compatible) ──────────────

    def register_agent(self, name: str, handler: Callable):
        if not name:
            raise ValueError("Agent name must be non-empty")
        if not callable(handler):
            raise TypeError("Handler must be callable")
        self._handlers[name] = handler

    def unregister_agent(self, name: str):
        self._handlers.pop(name, None)

    def list_agents(self) -> List[str]:
        return sorted(self._handlers.keys())

    async def run_task(self, task: TeamTask) -> TeamExecution:
        handler = self._handlers.get(task.agent_name)
        if handler is None:
            return TeamExecution(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TeamTaskStatus.FAILED,
                error=f"unregistered_agent:{task.agent_name}",
            )

        start = time.monotonic()
        try:
            coro = handler(task.payload) if asyncio.iscoroutinefunction(handler) \
                else asyncio.to_thread(handler, task.payload)

            if task.timeout_s:
                result = await asyncio.wait_for(coro, timeout=task.timeout_s)
            else:
                result = await coro

            return TeamExecution(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TeamTaskStatus.COMPLETED,
                result=result,
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except asyncio.TimeoutError:
            return TeamExecution(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TeamTaskStatus.TIMEOUT,
                error="task_timeout",
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return TeamExecution(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TeamTaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )

    async def run_batch(
        self,
        tasks: List[TeamTask],
        fail_fast: bool = False,
    ) -> List[TeamExecution]:
        results: List[Optional[TeamExecution]] = [None] * len(tasks)
        sem = asyncio.Semaphore(self._max_parallel)
        failed = False

        async def _run(idx: int, task: TeamTask):
            nonlocal failed
            if fail_fast and failed:
                results[idx] = TeamExecution(
                    task_id=task.task_id,
                    agent_name=task.agent_name,
                    status=TeamTaskStatus.CANCELLED,
                    error="fail_fast",
                )
                return
            async with sem:
                if fail_fast and failed:
                    results[idx] = TeamExecution(
                        task_id=task.task_id,
                        agent_name=task.agent_name,
                        status=TeamTaskStatus.CANCELLED,
                        error="fail_fast",
                    )
                    return
                result = await self.run_task(task)
                results[idx] = result
                if result.status == TeamTaskStatus.FAILED and fail_fast:
                    failed = True

        await asyncio.gather(*[_run(i, t) for i, t in enumerate(tasks)])
        return results  # type: ignore[return-value]

    async def coordinate(
        self,
        tasks: List[TeamTask],
        strategy: str = "all_success",
    ) -> Dict[str, Any]:
        results = await self.run_batch(tasks)
        return self.reduce_results(results, strategy=strategy)

    def reduce_results(
        self,
        results: List[TeamExecution],
        strategy: str = "all_success",
    ) -> Dict[str, Any]:
        if strategy == "first_success":
            for r in results:
                if r.status == TeamTaskStatus.COMPLETED:
                    return {"success": True, "winner": {"task_id": r.task_id, "result": r.result}}
            return {"success": False, "error": "no_successful_results"}

        elif strategy == "all_success":
            failed = [r for r in results if r.status != TeamTaskStatus.COMPLETED]
            return {
                "success": len(failed) == 0,
                "failed_count": len(failed),
                "results": [{"task_id": r.task_id, "result": r.result} for r in results],
            }

        elif strategy == "merge_dict":
            merged: Dict[str, Any] = {}
            for r in results:
                if r.status == TeamTaskStatus.COMPLETED and isinstance(r.result, dict):
                    merged.update(r.result)
            return {"success": bool(merged), "merged": merged}

        elif strategy == "review":
            all_findings: List[Any] = []
            for r in results:
                if r.status == TeamTaskStatus.COMPLETED and isinstance(r.result, dict):
                    all_findings.extend(r.result.get("findings", []))
            findings = ReviewReducer.merge_findings(all_findings)
            summary = ReviewReducer.summarize(findings)
            return {
                "success": not summary.should_block,
                "review": {
                    "should_block": summary.should_block,
                    "counts": summary.counts,
                    "highest_severity": summary.highest_severity,
                    "findings": [
                        {"severity": f.severity.name.lower(), "message": f.message}
                        for f in findings
                    ],
                },
            }

        raise ValueError(f"Unknown reduce strategy: {strategy}")
