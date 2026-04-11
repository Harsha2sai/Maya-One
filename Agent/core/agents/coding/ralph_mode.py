import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from core.agents.subagent.manager import SubAgentManager

logger = logging.getLogger(__name__)


@dataclass
class RalphState:
    task: str
    task_hash: int
    status: str = "running"  # running | completed | failed
    iteration: int = 0
    last_output: Optional[str] = None
    final_result: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class RalphResult:
    state: RalphState

    @property
    def succeeded(self) -> bool:
        return self.state.status == "completed"


class RalphExecutor:
    """
    $ralph mode: persistent execution with recovery loops.
    Loops until success or error threshold hit.
    State is persisted - survives crashes/restarts.
    """

    STORE_PATH = Path("/tmp/maya-ralph-states")

    def __init__(
        self,
        subagent_manager: SubAgentManager,
        store_path: Path = STORE_PATH,
    ):
        self.agents = subagent_manager
        self.store_path = store_path
        self.store_path.mkdir(parents=True, exist_ok=True)
        self._sleep = asyncio.sleep

    async def run(
        self,
        task: str,
        agent_type: str = "coder",
        max_iterations: int = 10,
        error_threshold: int = 3,
    ) -> RalphResult:
        """
        Execute task with recovery loop.
        Resumes from persisted state if interrupted.
        """
        state = await self._load_or_create(task)
        consecutive_errors = 0

        logger.info(
            "ralph_start task_hash=%s iteration=%s status=%s",
            state.task_hash,
            state.iteration,
            state.status,
        )

        while state.iteration < max_iterations:
            try:
                instance = await self.agents.spawn(
                    agent_type=agent_type,
                    task=self._build_iteration_task(task, state),
                    wait=True,
                )

                if instance.status.value == "completed":
                    consecutive_errors = 0
                    state.iteration += 1
                    state.last_output = instance.result

                    if self._is_terminal(instance.result):
                        state.status = "completed"
                        state.final_result = instance.result
                        break
                else:
                    raise RuntimeError(
                        f"Agent failed: {instance.error or 'unknown error'}"
                    )

            except Exception as e:
                consecutive_errors += 1
                state.errors.append(str(e))
                logger.warning(
                    "ralph_iteration_error iteration=%s consecutive=%s: %s",
                    state.iteration,
                    consecutive_errors,
                    e,
                )

                if consecutive_errors >= error_threshold:
                    state.status = "failed"
                    logger.error("ralph_failed task_hash=%s", state.task_hash)
                    break

                backoff = min(2 ** consecutive_errors, 30)
                await self._sleep(backoff)

            finally:
                state.updated_at = datetime.utcnow().isoformat()
                await self._persist(state)

        if state.status == "running":
            state.status = "failed"
            await self._persist(state)

        return RalphResult(state=state)

    async def get_state(self, task: str) -> Optional[RalphState]:
        """Check state of a previously started ralph task."""
        task_hash = hash(task)
        state_file = self.store_path / f"{task_hash}.json"
        if state_file.exists():
            data = json.loads(state_file.read_text())
            return RalphState(**data)
        return None

    def _build_iteration_task(self, original_task: str, state: RalphState) -> str:
        if state.iteration == 0 or not state.last_output:
            return original_task
        return (
            f"{original_task}\n\n"
            f"Previous attempt (iteration {state.iteration}) produced:\n"
            f"{state.last_output}\n\n"
            "Continue and improve."
        )

    def _is_terminal(self, result: Optional[str]) -> bool:
        """Determine if the result indicates task completion."""
        if not result:
            return False
        result_lower = result.lower()
        terminal_signals = (
            "complete",
            "done",
            "finished",
            "implemented",
            "def ",
            "class ",
        )
        return any(sig in result_lower for sig in terminal_signals)

    async def _load_or_create(self, task: str) -> RalphState:
        existing = await self.get_state(task)
        if existing and existing.status == "running":
            logger.info("ralph_resume task_hash=%s", existing.task_hash)
            return existing
        return RalphState(task=task, task_hash=hash(task))

    async def _persist(self, state: RalphState):
        state_file = self.store_path / f"{state.task_hash}.json"
        state_file.write_text(json.dumps(asdict(state), indent=2))
