import asyncio
import logging
import sys
import os

# Ensure we can find core modules
sys.path.append(os.getcwd())

from core.tasks.task_worker import TaskWorker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def main():
    user_id = "preflight_user"
    logger.info(f"Starting Standalone TaskWorker for user {user_id}")
    
    try:
        worker = TaskWorker(user_id, interval=1.0)
        await worker.start()
        
        # Run forever until cancelled
        while True:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        logger.info("Stopping worker...")
        await worker.stop()
    except Exception as e:
        logger.error(f"Worker crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
