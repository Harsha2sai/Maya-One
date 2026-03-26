import concurrent.futures
import os
import shutil
import sys
import threading
import types

import pytest
from core.memory.vector_store import VectorStore
from core.memory.memory_models import MemoryItem, MemorySource

class _FakeEmbeddingModel:
    _VOCAB = (
        "python",
        "javascript",
        "programming",
        "language",
        "web",
        "paris",
        "eiffel",
        "coding",
    )
    _ALIASES = {
        "languages": "language",
        "programmer": "programming",
        "coding": "programming",
    }

    def encode(self, text: str):
        lowered = (text or "").lower()
        tokens = [self._ALIASES.get(token.strip(".,!?"), token.strip(".,!?")) for token in lowered.split()]
        vector = [0.0] * len(self._VOCAB)
        for index, term in enumerate(self._VOCAB):
            vector[index] = float(tokens.count(term))
        return vector

@pytest.fixture
def temp_vector_store(tmp_path):
    """Create a temporary vector store for testing."""
    store = VectorStore(persist_directory=str(tmp_path / "chroma"))
    store._embedding_model = _FakeEmbeddingModel()
    yield store
    # Cleanup
    if os.path.exists(tmp_path):
        shutil.rmtree(tmp_path)

def test_vector_store_initialization(temp_vector_store):
    """Test that vector store initializes correctly."""
    assert temp_vector_store.collection is not None
    assert temp_vector_store.embedding_model is not None

def test_add_memory(temp_vector_store):
    """Test adding a memory to vector store."""
    memory = MemoryItem(
        text="The capital of France is Paris",
        source=MemorySource.CONVERSATION,
        metadata={"topic": "geography"}
    )
    
    success = temp_vector_store.add_memory(memory)
    assert success is True
    assert temp_vector_store.count() == 1

def test_similarity_search(temp_vector_store):
    """Test semantic similarity search."""
    # Add test memories
    memories = [
        MemoryItem(text="Python is a programming language", source=MemorySource.CONVERSATION),
        MemoryItem(text="JavaScript is used for web development", source=MemorySource.CONVERSATION),
        MemoryItem(text="The Eiffel Tower is in Paris", source=MemorySource.CONVERSATION),
    ]
    
    for mem in memories:
        temp_vector_store.add_memory(mem)
    
    # Search for programming-related content
    results = temp_vector_store.similarity_search("coding languages", k=2)
    
    assert len(results) > 0
    assert len(results) <= 2
    # Should return programming-related memories
    assert any("Python" in r['text'] or "JavaScript" in r['text'] for r in results)

def test_delete_memory(temp_vector_store):
    """Test deleting a memory."""
    memory = MemoryItem(
        text="Test memory",
        source=MemorySource.CONVERSATION
    )
    
    temp_vector_store.add_memory(memory)
    assert temp_vector_store.count() == 1
    
    temp_vector_store.delete_memory(memory.id)
    assert temp_vector_store.count() == 0


def test_vector_store_concurrent_init_is_safe(tmp_path, monkeypatch):
    init_calls = {"count": 0}
    call_lock = threading.Lock()

    class _FakeSentenceTransformer:
        def __init__(self, _model_name: str) -> None:
            with call_lock:
                init_calls["count"] += 1

        def encode(self, _text: str):
            return [0.0, 0.0, 0.0]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer),
    )

    store = VectorStore(persist_directory=str(tmp_path / "chroma"), model_name="fake-model")
    model_ids = []

    def _access_model() -> None:
        model = store.embedding_model
        with call_lock:
            model_ids.append(id(model))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_access_model) for _ in range(50)]
        concurrent.futures.wait(futures)

    assert len(set(model_ids)) == 1
    assert init_calls["count"] == 1
