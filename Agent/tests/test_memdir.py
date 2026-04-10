import json
from pathlib import Path

import pytest

from core.memory.memdir import AgentContextStore, SessionStore, UserPreferences
from core.runtime.global_agent import GlobalAgentContainer


def test_session_store_save_load_roundtrip(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    store.save("session-1", {"turn": 3, "topic": "hooks"})

    loaded = store.load("session-1")

    assert loaded is not None
    assert loaded["session_id"] == "session-1"
    assert loaded["data"] == {"turn": 3, "topic": "hooks"}
    assert "updated_at" in loaded


def test_session_store_list_sessions_sorted(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    store.save("b-session", {"x": 1})
    store.save("a-session", {"x": 2})

    assert store.list_sessions() == ["a-session", "b-session"]


def test_session_store_delete_existing_and_missing(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    store.save("s1", {"ok": True})

    assert store.delete("s1") is True
    assert store.delete("s1") is False


def test_session_store_load_missing_returns_none(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))

    assert store.load("missing") is None


def test_session_store_requires_non_empty_session_id(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError):
        store.save("", {"x": 1})

    with pytest.raises(ValueError):
        store.load("   ")


def test_session_store_overwrites_existing_session(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    store.save("s1", {"v": 1})
    store.save("s1", {"v": 2})

    loaded = store.load("s1")
    assert loaded["data"] == {"v": 2}


def test_session_store_atomic_write_leaves_no_temp_files(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    store.save("s1", {"x": 1})

    session_dir = Path(tmp_path) / "sessions"
    temp_files = [p for p in session_dir.iterdir() if p.name.startswith(".s1.json.")]
    assert temp_files == []


def test_user_preferences_set_get_get_all(tmp_path):
    prefs = UserPreferences(base_dir=str(tmp_path))
    prefs.set("user-1", "theme", "dark")
    prefs.set("user-1", "language", "en")

    assert prefs.get("user-1", "theme") == "dark"
    assert prefs.get("user-1", "missing", default="fallback") == "fallback"
    assert prefs.get_all("user-1") == {"theme": "dark", "language": "en"}


def test_user_preferences_delete_key_and_file(tmp_path):
    prefs = UserPreferences(base_dir=str(tmp_path))
    prefs.set("u1", "k1", "v1")
    prefs.set("u1", "k2", "v2")

    assert prefs.delete("u1", "k1") is True
    assert prefs.get_all("u1") == {"k2": "v2"}
    assert prefs.delete("u1") is True
    assert prefs.get_all("u1") == {}


def test_user_preferences_delete_missing_returns_false(tmp_path):
    prefs = UserPreferences(base_dir=str(tmp_path))

    assert prefs.delete("missing") is False
    prefs.set("u1", "k", "v")
    assert prefs.delete("u1", "missing-key") is False


def test_user_preferences_requires_user_and_key(tmp_path):
    prefs = UserPreferences(base_dir=str(tmp_path))

    with pytest.raises(ValueError):
        prefs.set("", "k", "v")

    with pytest.raises(ValueError):
        prefs.set("u", "", "v")


def test_user_preferences_atomic_write_json_file_shape(tmp_path):
    prefs = UserPreferences(base_dir=str(tmp_path))
    prefs.set("u1", "timezone", "UTC")

    path = Path(tmp_path) / "prefs" / "u1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["user_id"] == "u1"
    assert payload["values"] == {"timezone": "UTC"}


def test_agent_context_store_save_load_clear(tmp_path):
    store = AgentContextStore(base_dir=str(tmp_path))
    store.save_context("agent-1", {"handoff_id": "h1", "depth": 2})

    loaded = store.load_context("agent-1")
    assert loaded is not None
    assert loaded["agent_id"] == "agent-1"
    assert loaded["context"] == {"handoff_id": "h1", "depth": 2}

    assert store.clear_context("agent-1") is True
    assert store.load_context("agent-1") is None


def test_agent_context_store_clear_missing_returns_false(tmp_path):
    store = AgentContextStore(base_dir=str(tmp_path))

    assert store.clear_context("missing") is False


def test_agent_context_store_requires_agent_id(tmp_path):
    store = AgentContextStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError):
        store.save_context("", {"x": 1})

    with pytest.raises(ValueError):
        store.load_context("   ")


def test_agent_context_store_overwrites_existing(tmp_path):
    store = AgentContextStore(base_dir=str(tmp_path))
    store.save_context("agent-1", {"state": 1})
    store.save_context("agent-1", {"state": 2})

    loaded = store.load_context("agent-1")
    assert loaded["context"] == {"state": 2}


def test_memdir_directories_are_created(tmp_path):
    SessionStore(base_dir=str(tmp_path))
    UserPreferences(base_dir=str(tmp_path))
    AgentContextStore(base_dir=str(tmp_path))

    assert (Path(tmp_path) / "sessions").exists()
    assert (Path(tmp_path) / "prefs").exists()
    assert (Path(tmp_path) / "contexts").exists()


def test_global_agent_container_getters_return_wired_instances(tmp_path):
    session_store = SessionStore(base_dir=str(tmp_path))
    prefs_store = UserPreferences(base_dir=str(tmp_path))

    original_session = GlobalAgentContainer._session_store
    original_prefs = GlobalAgentContainer._user_preferences_store
    try:
        GlobalAgentContainer._session_store = session_store
        GlobalAgentContainer._user_preferences_store = prefs_store

        assert GlobalAgentContainer.get_session_store() is session_store
        assert GlobalAgentContainer.get_user_preferences_store() is prefs_store
    finally:
        GlobalAgentContainer._session_store = original_session
        GlobalAgentContainer._user_preferences_store = original_prefs


def test_session_and_context_stores_use_separate_namespaces(tmp_path):
    session_store = SessionStore(base_dir=str(tmp_path))
    context_store = AgentContextStore(base_dir=str(tmp_path))

    session_store.save("id-1", {"session": True})
    context_store.save_context("id-1", {"context": True})

    assert (Path(tmp_path) / "sessions" / "id-1.json").exists()
    assert (Path(tmp_path) / "contexts" / "id-1.json").exists()
