
from core.tasks.workers.base import BaseWorker
from core.tasks.task_steps import WorkerType

class ResearchWorker(BaseWorker):
    def __init__(self, user_id, store, memory_manager=None, smart_llm=None, room=None):
        super().__init__(user_id, store, memory_manager, smart_llm, room=room)
        self.worker_type = WorkerType.RESEARCH

    def get_system_prompt(self, task, step):
        return """
        You are the Research Worker.
        Your role is to gather information, analyze data, and summarize findings.
        You are thorough, objective, and cite sources where possible.
        NOTE: You can browse the web but cannot control the local system or create files.
        """
