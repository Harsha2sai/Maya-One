from core.memory.hybrid_memory_manager import HybridMemoryManager
from core.context.context_builder import ContextBuilder
# Check if TaskManager import is needed for test setup?
# ContextBuilder creates it internally.

def test_task_manager_injected():
    # Mock mocks
    class MockMemory:
        pass
    
    memory = MockMemory()
    # ContextBuilder(llm, memory_manager, user_id, rolling_manager)
    ctx = ContextBuilder(llm=None, memory_manager=memory, user_id="test_user")
    
    # Check if task_manager is initialized
    assert ctx.task_manager is not None
    # Check if memory_manager is injected
    assert ctx.task_manager.memory is memory
    print("PASS: TaskManager injected with memory_manager")

if __name__ == "__main__":
    test_task_manager_injected()
