import os

# Ensure DB connection BEFORE other imports
os.environ["DATABASE_URL"] = "sqlite:///dev_maya_one.db"

from core.orchestrator.agent_orchestrator import AgentOrchestrator
import asyncio

async def main():
    # Mock dependencies
    from unittest.mock import MagicMock
    mock_ctx = MagicMock()
    mock_agent = MagicMock()
    mock_agent.user_id = "maya_validation_user"
    
    orchestrator = AgentOrchestrator(mock_ctx, mock_agent)
    
    try:
        # Check actual method name from file view: handle_intent seems to be the main public API. 
        # create_task_from_user_intent doesn't exist in the viewed file.
        # But the plan said "create_task_from_user_intent". 
        # I will use handle_intent as it is the one implemented.
        # Wait, handle_intent returns a string. The user wanted a Task object.
        # Logic in handle_intent: 
        #   steps = await self.planning_engine.generate_plan(user_text)
        #   task = Task(...)
        #   success = await self.task_store.create_task(task)
        #   return string
        # To get the task object, we might need to query the DB or modify the return.
        # For this script, since the user wants to print the task ID, and handle_intent doesn't return it,
        # we should query the DB after handle_intent returns.
        
        response = await orchestrator.handle_intent("Write a short report about AI agents")
        print(f"Orchestrator Response: {response}")
        
        # Query DB to get the task
        import sqlite3
        with sqlite3.connect("dev_maya_one.db") as conn:
            cursor = conn.execute("SELECT id FROM tasks ORDER BY created_at DESC LIMIT 1")
            task_id = cursor.fetchone()[0]
            print("Created task:", task_id)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
