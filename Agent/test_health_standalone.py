import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from agent import run_health_checks

if __name__ == "__main__":
    asyncio.run(run_health_checks())
    print("FINISHED_HEALTH_CHECKS")
