from enum import Enum

class MayaRuntimeMode(str, Enum):
    CONSOLE = "console"
    WORKER = "worker"

# Global state to be set at application startup
# Default to WORKER to be safe for production
CURRENT_MODE: MayaRuntimeMode = MayaRuntimeMode.WORKER
