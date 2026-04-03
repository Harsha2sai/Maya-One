import asyncio
import pytest
import os
import shutil
from core.memory.hybrid_memory_manager import HybridMemoryManager
from core.memory.memory_models import MemorySource

class _FakeEmbeddingModel:
    _VOCAB = (
        "python",
        "javascript",
        "programming",
        "language",
        "web",
        "data",
        "processing",
        "analysis",
    )
    _ALIASES = {
        "coding": "programming",
        "languages": "language",
    }

    def encode(self, text: str):
        lowered = (text or "").lower()
        tokens = [self._ALIASES.get(token.strip(".,!?"), token.strip(".,!?")) for token in lowered.split()]
        vector = [0.0] * len(self._VOCAB)
        for index, term in enumerate(self._VOCAB):
            vector[index] = float(tokens.count(term))
        return vector

@pytest.fixture
def temp_memory_manager(tmp_path, monkeypatch):
    """Create a temporary memory manager for testing."""
    # Override default paths to use tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))
    manager = HybridMemoryManager()
    manager.retriever.vector_store._embedding_model = _FakeEmbeddingModel()
    yield manager
    # Cleanup
    if os.path.exists(tmp_path):
        shutil.rmtree(tmp_path)

def test_memory_manager_initialization(temp_memory_manager):
    """Test that memory manager initializes correctly."""
    assert temp_memory_manager.retriever is not None

def test_store_conversation_turn(temp_memory_manager):
    """Test storing a conversation turn."""
    success = asyncio.run(temp_memory_manager.store_conversation_turn(
        user_msg="What is Python?",
        assistant_msg="Python is a high-level programming language.",
        metadata={"session_id": "test123"}
    ))
    
    assert success is True
    stats = temp_memory_manager.get_stats()
    assert stats['vector_count'] == 1
    assert stats['keyword_count'] == 1

def test_store_conversation_turn_persists_user_and_session_scope(temp_memory_manager):
    """Conversation turns should persist user/session metadata for scoped retrieval."""
    success = asyncio.run(temp_memory_manager.store_conversation_turn(
        user_msg="my name is Harsha",
        assistant_msg="Nice to meet you, Harsha.",
        metadata={"source": "conversation", "role": "chat"},
        user_id="console_user",
        session_id="console-room",
    ))

    assert success is True
    stored = temp_memory_manager.retriever.vector_store.collection.get(
        where={"$and": [{"user_id": "console_user"}, {"session_id": "console-room"}]},
        include=["metadatas", "documents"],
    )
    assert len(stored["ids"]) >= 1
    matched = None
    for meta in (stored.get("metadatas") or []):
        if isinstance(meta, dict) and meta.get("role") == "chat":
            matched = meta
            break
    assert matched is not None
    assert matched["user_id"] == "console_user"
    assert matched["session_id"] == "console-room"

def test_store_conversation_turn_extracts_profile_fact_for_name_statement(temp_memory_manager):
    success = asyncio.run(temp_memory_manager.store_conversation_turn(
        user_msg="my name is Harsha",
        assistant_msg="Nice to meet you.",
        user_id="console_user",
        session_id="console-room",
    ))
    assert success is True

    profile_rows = temp_memory_manager.retriever.vector_store.collection.get(
        where={"$and": [{"user_id": "console_user"}, {"memory_kind": "profile_fact"}]},
        include=["metadatas", "documents"],
    )
    assert len(profile_rows["ids"]) >= 1
    assert any("name=Harsha" in str(doc or "") for doc in (profile_rows.get("documents") or []))

def test_duplicate_conversation_write_guard_skips_repeated_user_turn(temp_memory_manager):
    first = asyncio.run(temp_memory_manager.store_conversation_turn(
        user_msg="repeat this question",
        assistant_msg="first answer",
        user_id="console_user",
        session_id="console-room",
    ))
    second = asyncio.run(temp_memory_manager.store_conversation_turn(
        user_msg="repeat this question",
        assistant_msg="second answer should be deduped",
        user_id="console_user",
        session_id="console-room",
    ))
    assert first is True
    assert second is True

    rows = temp_memory_manager.retriever.vector_store.collection.get(
        where={"$and": [{"user_id": "console_user"}, {"session_id": "console-room"}]},
        include=["documents"],
    )
    docs = [str(doc or "") for doc in (rows.get("documents") or [])]
    assert len(docs) == 1
    assert "first answer" in docs[0]

def test_store_task_result(temp_memory_manager):
    """Test storing a task result."""
    success = temp_memory_manager.store_task_result(
        task_id="task-123",
        result="Successfully completed data analysis task",
        metadata={"duration": "5m"}
    )
    
    assert success is True

def test_store_tool_output(temp_memory_manager):
    """Test storing tool output."""
    success = temp_memory_manager.store_tool_output(
        tool_name="web_search",
        output="Found 10 relevant articles about AI",
        metadata={"query": "artificial intelligence"}
    )
    
    assert success is True

def test_retrieve_relevant_memories(temp_memory_manager):
    """Test retrieving relevant memories."""
    # Store some memories
    asyncio.run(temp_memory_manager.store_conversation_turn(
        "Tell me about Python",
        "Python is a programming language"
    ))
    asyncio.run(temp_memory_manager.store_conversation_turn(
        "What about JavaScript?",
        "JavaScript is used for web development"
    ))
    temp_memory_manager.store_task_result(
        "task-1",
        "Completed Python script for data processing"
    )
    
    # Retrieve memories related to Python
    memories = temp_memory_manager.retrieve_relevant_memories("Python programming", k=2)
    
    assert len(memories) > 0
    assert len(memories) <= 2
    assert all('rrf_score' in m for m in memories)

def test_get_stats(temp_memory_manager):
    """Test getting memory statistics."""
    asyncio.run(temp_memory_manager.store_conversation_turn("Hello", "Hi there"))
    temp_memory_manager.store_task_result("task-1", "Done")
    
    stats = temp_memory_manager.get_stats()
    assert 'vector_count' in stats
    assert 'keyword_count' in stats
    assert stats['vector_count'] == 2
    assert stats['keyword_count'] == 2
