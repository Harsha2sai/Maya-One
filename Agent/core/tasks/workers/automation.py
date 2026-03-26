
from core.tasks.workers.base import BaseWorker
from core.tasks.task_steps import WorkerType

class AutomationWorker(BaseWorker):
    def __init__(self, user_id, store, memory_manager=None, smart_llm=None, room=None):
        super().__init__(user_id, store, memory_manager, smart_llm, room=room)
        self.worker_type = WorkerType.AUTOMATION

    def get_system_prompt(self, task, step):
        return """
        You are the Automation Worker.
        Your role is to execute complex tool workflows and integrations (Email, Calendar, etc).
        You are precise and careful with tool parameters.
        NOTE: You execute actions. Do not hallucinate capabilities you don't have.
        """
