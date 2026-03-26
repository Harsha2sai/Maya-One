
from core.tasks.workers.base import BaseWorker
from core.tasks.task_steps import WorkerType

class SystemWorker(BaseWorker):
    def __init__(self, user_id, store, memory_manager=None, smart_llm=None, room=None):
        super().__init__(user_id, store, memory_manager, smart_llm, room=room)
        self.worker_type = WorkerType.SYSTEM

    def get_system_prompt(self, task, step):
        return """
        You are the System Worker.
        Your role is to interact with the local operating system, filesystem, and terminal.
        You have high privileges (Shell, File I/O). ACT RESPONSIBLY.
        Verify commands before execution.
        """
