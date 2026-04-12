# OpenClaw-style Hybrid Memory System (new)
from .memory_models import MemoryItem, MemorySource
from .vector_store import VectorStore
from .keyword_store import KeywordStore
from .hybrid_retriever import HybridRetriever
from .hybrid_memory_manager import HybridMemoryManager
from .agentscope_store import MayaAgentScopeMemory

# Legacy Mem0-based system (optional, requires mem0 package)
# from .memory_manager import MemoryManager
# from .local_engine import LocalMemoryEngine
