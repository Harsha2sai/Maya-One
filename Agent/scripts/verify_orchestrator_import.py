
import sys
import asyncio
from unittest.mock import MagicMock

async def main():
    try:
        sys.path.append('.') # Add current dir to path
        from core.orchestrator.agent_orchestrator import AgentOrchestrator
        print("Import successful")
        # Mock dependencies if needed, but __init__ just inits them.
        # Ensure we can instantiate
        orch = AgentOrchestrator(MagicMock(), MagicMock())
        print("Instantiation successful")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
