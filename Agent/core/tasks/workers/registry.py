
import logging
from typing import Dict, Type, Any

from core.tasks.task_steps import WorkerType
from core.tasks.workers.base import BaseWorker
from core.tasks.workers.general import GeneralWorker
from core.tasks.workers.research import ResearchWorker
from core.tasks.workers.automation import AutomationWorker
from core.tasks.workers.system import SystemWorker
from core.tasks.task_store import TaskStore

logger = logging.getLogger(__name__)

class WorkerRegistry:
    """
    Factory for creating/retrieving worker instances.
    """
    _workers: Dict[WorkerType, BaseWorker] = {}

    def __init__(
        self,
        user_id: str,
        store: TaskStore,
        memory_manager: Any = None,
        smart_llm: Any = None,
        room: Any = None,
    ):
        self.user_id = user_id
        self.store = store
        self.memory_manager = memory_manager
        self.smart_llm = smart_llm
        self.room = room
        self._initialize_workers()

    def _initialize_workers(self):
        """Instantiate all worker types."""
        self._workers = {
            WorkerType.GENERAL: GeneralWorker(
                self.user_id,
                self.store,
                self.memory_manager,
                self.smart_llm,
                room=self.room,
            ),
            WorkerType.RESEARCH: ResearchWorker(
                self.user_id,
                self.store,
                self.memory_manager,
                self.smart_llm,
                room=self.room,
            ),
            WorkerType.AUTOMATION: AutomationWorker(
                self.user_id,
                self.store,
                self.memory_manager,
                self.smart_llm,
                room=self.room,
            ),
            WorkerType.SYSTEM: SystemWorker(
                self.user_id,
                self.store,
                self.memory_manager,
                self.smart_llm,
                room=self.room,
            ),
        }

    def get_worker(self, worker_type: WorkerType) -> BaseWorker:
        """Get the worker instance for the given type."""
        worker = self._workers.get(worker_type)
        if not worker:
            logger.warning(f"Worker type {worker_type} not found, falling back to GENERAL")
            return self._workers[WorkerType.GENERAL]
        return worker

    def update_room(self, room: Any) -> None:
        self.room = room
        for worker in self._workers.values():
            worker.set_room(room)
