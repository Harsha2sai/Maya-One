from enum import Enum, auto

class AgentMode(Enum):
    SAFE = auto()   # Heuristic-first, governed execution (Default)
    DIRECT = auto() # Raw LLM tool calling, still audited/gated
