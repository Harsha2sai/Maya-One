
# Global safety limits for the Autonomous Agent System

# Maximum number of tasks that can be in RUNNING/PENDING state simultaneously
MAX_ACTIVE_TASKS = 5

# Maximum number of steps a single task is allowed to execute
MAX_STEPS_PER_TASK = 20

# Maximum number of times a task can delegate sub-tasks (to prevent explosion)
MAX_DELEGATIONS_PER_TASK = 5

# Maximum nested delegation depth (A -> B -> C -> D)
MAX_DELEGATION_DEPTH = 3

# Maximum runtime for a task in seconds (30 minutes)
MAX_TASK_RUNTIME_SECONDS = 1800

# Maximum retries per step
MAX_STEP_RETRIES = 2

# Tool Execution Timeouts (Seconds)
TOOL_TIMEOUTS = {
    "web": 15,
    "automation": 20,
    "system": 10,
    "default": 30
}
