
from core.tasks.workers.base import BaseWorker
from core.tasks.task_steps import WorkerType

class GeneralWorker(BaseWorker):
    def __init__(self, user_id, store, memory_manager=None, smart_llm=None, room=None):
        super().__init__(user_id, store, memory_manager, smart_llm, room=room)
        self.worker_type = WorkerType.GENERAL

    def get_system_prompt(self, task, step):
        return """
        You are the General Worker.
        Your role is to handle general reasoning, planning, and conversation tasks.
        You are logical, clear, and efficient.
        NOTE: You have limited tool access. You cannot perform system operations or heavy research. Delegate/Plan for those.
        """
