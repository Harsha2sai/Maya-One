import pytest
import os
import shutil
from core.memory.keyword_store import KeywordStore
from core.memory.memory_models import MemoryItem, MemorySource

@pytest.fixture
def temp_keyword_store(tmp_path):
    """Create a temporary keyword store for testing."""
    db_path = str(tmp_path / "keyword.db")
    store = KeywordStore(db_path=db_path)
    yield store
    # Cleanup
    if os.path.exists(tmp_path):
        shutil.rmtree(tmp_path)

def test_keyword_store_initialization(temp_keyword_store):
    """Test that keyword store initializes correctly."""
    assert temp_keyword_store.db_path is not None
    assert os.path.exists(temp_keyword_store.db_path)

def test_add_memory(temp_keyword_store):
    """Test adding a memory to keyword store."""
    memory = MemoryItem(
        text="The quick brown fox jumps over the lazy dog",
        source=MemorySource.CONVERSATION,
        metadata={"category": "test"}
    )
    
    success = temp_keyword_store.add_memory(memory)
    assert success is True
    assert temp_keyword_store.count() == 1

def test_keyword_search(temp_keyword_store):
    """Test FTS5 keyword search."""
    # Add test memories
    memories = [
        MemoryItem(text="Python programming tutorial for beginners", source=MemorySource.FILE),
        MemoryItem(text="JavaScript web development guide", source=MemorySource.FILE),
        MemoryItem(text="Advanced Python data structures", source=MemorySource.FILE),
    ]
    
    for mem in memories:
        temp_keyword_store.add_memory(mem)
    
    # Search for "Python"
    results = temp_keyword_store.keyword_search("Python", k=5)
    
    assert len(results) == 2
    assert all("Python" in r['text'] for r in results)

def test_delete_memory(temp_keyword_store):
    """Test deleting a memory."""
    memory = MemoryItem(
        text="Test memory for deletion",
        source=MemorySource.CONVERSATION
    )
    
    temp_keyword_store.add_memory(memory)
    assert temp_keyword_store.count() == 1
    
    temp_keyword_store.delete_memory(memory.id)
    assert temp_keyword_store.count() == 0
