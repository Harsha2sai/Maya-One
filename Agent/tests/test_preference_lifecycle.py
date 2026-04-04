import pytest

from core.memory.preference_manager import PreferenceManager


@pytest.fixture
def patched_preference_manager(tmp_path, monkeypatch):
    pm = PreferenceManager()

    def _user_file(user_id: str):
        return tmp_path / f"{user_id}.json"

    monkeypatch.setattr(pm, "_user_file", _user_file)
    return pm


@pytest.mark.asyncio
async def test_set_and_get(patched_preference_manager):
    pm = patched_preference_manager
    user_id = "user_set_get"
    await pm.set(user_id, "music_app", "spotify")
    prefs = await pm.get_all(user_id)
    assert prefs.get("music_app") == "spotify"


@pytest.mark.asyncio
async def test_update_overwrites(patched_preference_manager):
    pm = patched_preference_manager
    user_id = "user_update"
    await pm.set(user_id, "music_app", "spotify")
    await pm.set(user_id, "music_app", "youtube")
    prefs = await pm.get_all(user_id)
    assert prefs.get("music_app") == "youtube"


@pytest.mark.asyncio
async def test_missing_file_returns_empty(patched_preference_manager):
    pm = patched_preference_manager
    user_id = "user_missing"
    prefs = await pm.get_all(user_id)
    assert prefs == {}


@pytest.mark.asyncio
async def test_corrupt_file_returns_empty(patched_preference_manager, tmp_path):
    pm = patched_preference_manager
    user_id = "user_corrupt"
    corrupt_path = tmp_path / f"{user_id}.json"
    corrupt_path.write_text("{not: valid json}", encoding="utf-8")
    prefs = await pm.get_all(user_id)
    assert prefs == {}


@pytest.mark.asyncio
async def test_extract_from_text_music_app(patched_preference_manager):
    pm = patched_preference_manager
    user_id = "user_extract"
    await pm.extract_from_text("I use spotify for music", user_id)
    prefs = await pm.get_all(user_id)
    assert prefs.get("music_app") == "spotify"


@pytest.mark.asyncio
async def test_extract_from_text_no_match(patched_preference_manager):
    pm = patched_preference_manager
    user_id = "user_no_match"
    await pm.extract_from_text("what time is it", user_id)
    prefs = await pm.get_all(user_id)
    assert prefs == {}
