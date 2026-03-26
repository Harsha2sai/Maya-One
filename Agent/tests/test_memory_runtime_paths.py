import importlib
from pathlib import Path

import pytest

settings_mod = importlib.import_module("config.settings")
from config.settings import settings
from core.memory.keyword_store import KeywordStore
from core.memory.vector_store import VectorStore
from core.observability.behavioral_sentinel import BehavioralSentinel
from core.runtime import startup_health_probes
from core.runtime.global_agent import GlobalAgentContainer, MemoryRootError, _validate_memory_root_writable


def test_memory_root_defaults_to_agent_local_path(monkeypatch):
    monkeypatch.delenv("MAYA_MEMORY_ROOT", raising=False)

    expected = Path(settings_mod.__file__).resolve().parents[1] / ".maya" / "memory"

    assert settings.memory_root == expected.resolve()


def test_memory_root_honors_env_override(monkeypatch, tmp_path):
    custom_root = tmp_path / "custom-memory-root"
    monkeypatch.setenv("MAYA_MEMORY_ROOT", str(custom_root))

    assert settings.memory_root == custom_root.resolve()
    assert settings.keyword_db_path == (custom_root / "keyword.db").resolve()
    assert settings.chroma_persist_directory == (custom_root / "chroma").resolve()


def test_keyword_store_uses_settings_keyword_db_path(monkeypatch, tmp_path):
    custom_root = tmp_path / "keyword-store-root"
    monkeypatch.setenv("MAYA_MEMORY_ROOT", str(custom_root))

    store = KeywordStore()

    assert Path(store.db_path) == (custom_root / "keyword.db").resolve()


def test_vector_store_uses_settings_chroma_persist_directory(monkeypatch, tmp_path):
    custom_root = tmp_path / "vector-store-root"
    monkeypatch.setenv("MAYA_MEMORY_ROOT", str(custom_root))

    store = VectorStore()

    assert Path(store.persist_directory) == (custom_root / "chroma").resolve()


def test_global_agent_fails_fast_on_unwritable_memory_root(tmp_path, monkeypatch):
    locked_root = tmp_path / "locked"
    locked_root.mkdir()
    locked_root.chmod(0o000)
    monkeypatch.setenv("MAYA_MEMORY_ROOT", str(locked_root))

    try:
        with pytest.raises(MemoryRootError):
            _validate_memory_root_writable(locked_root)
    finally:
        locked_root.chmod(0o755)


@pytest.mark.asyncio
async def test_boot_probe_memory_uses_container_memory_manager(monkeypatch):
    class FakeMemory:
        def __init__(self):
            self.store_calls = 0
            self.retrieve_calls = 0

        def store_conversation_turn(self, user_msg, assistant_msg, metadata=None):
            self.store_calls += 1
            return True

        def retrieve_relevant_memories(self, query, k=5, user_id=None):
            self.retrieve_calls += 1
            return [{"text": "probe_value_12345"}]

    fake_memory = FakeMemory()

    class FakeContainer:
        @staticmethod
        def get_memory():
            return fake_memory

    async def fake_get_runtime_container():
        return FakeContainer

    monkeypatch.setattr(startup_health_probes, "_get_runtime_container", fake_get_runtime_container)

    passed, message = await startup_health_probes._probe_memory()

    assert passed is True
    assert "Memory write/read verified" in message
    assert fake_memory.store_calls == 1
    assert fake_memory.retrieve_calls == 1


@pytest.mark.asyncio
async def test_behavioral_sentinel_uses_container_memory_manager(monkeypatch):
    class FakeMemory:
        def __init__(self):
            self.store_calls = 0
            self.retrieve_calls = 0

        def store_conversation_turn(self, user_msg, assistant_msg, metadata=None):
            self.store_calls += 1
            return True

        def retrieve_relevant_memories(self, query, k=5, user_id=None):
            self.retrieve_calls += 1
            return [{"text": query}]

    fake_memory = FakeMemory()
    sentinel = BehavioralSentinel()
    events = []

    async def fail_initialize():
        raise AssertionError("initialize() should not run when the container is already initialized")

    def record_log(event, message, level="info", **kwargs):
        events.append((event, message, level, kwargs))

    monkeypatch.setattr(sentinel, "_log", record_log)
    monkeypatch.setattr(GlobalAgentContainer, "_initialized", True)
    monkeypatch.setattr(GlobalAgentContainer, "_memory", fake_memory)
    monkeypatch.setattr(GlobalAgentContainer, "initialize", fail_initialize)

    await sentinel._check_memory_persistence()

    assert fake_memory.store_calls == 1
    assert fake_memory.retrieve_calls == 1
    assert any(event == "sentinel_memory_ok" for event, *_ in events)
