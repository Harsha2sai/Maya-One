import asyncio
import logging
import os
from unittest.mock import patch, MagicMock
from core.tasks.task_worker import TaskWorker
from core.tasks.workers.base import ProviderFactory

# Mock LLM Response
class MockLLMStream:
    def __init__(self, text="Mock response summary."):
        self.text = text
    
    async def __aiter__(self):
        # yields a mock chunk
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = self.text
        yield chunk

def mock_get_llm(provider, model):
    mock_llm = MagicMock()
    mock_llm.chat.return_value = MockLLMStream()
    return mock_llm

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    user_id = os.getenv("USER_ID", "maya_validation_user")
    
    print(f"🛠️ Starting TaskWorker with MOCK LLM for user: {user_id}")
    logger = logging.getLogger("MockWorker")
    logger.info("Worker Process Started")
    
    try:
        # Patch ProviderFactory.get_llm and WorkerToolRegistry.is_tool_allowed
        from core.tasks.workers.tool_registry import WorkerToolRegistry
        with patch.object(ProviderFactory, 'get_llm', side_effect=mock_get_llm), \
             patch.object(WorkerToolRegistry, 'is_tool_allowed', return_value=True):
            worker = TaskWorker(user_id)
            await worker.start()
            logger.info("Worker Loop Running...")
            while True:
                await asyncio.sleep(10)
    except Exception as e:
        logger.error(f"FATAL: Worker crashed: {e}", exc_info=True)
    finally:
        logger.info("Worker Process Exiting")

if __name__ == "__main__":
    asyncio.run(main())
