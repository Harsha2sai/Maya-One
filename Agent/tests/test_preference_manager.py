import pytest

from core.memory.preference_manager import PreferenceManager


@pytest.mark.asyncio
async def test_preference_manager_local_set_get(tmp_path):
    manager = PreferenceManager(storage_path=str(tmp_path / "prefs"))
    user_id = "u-pref-1"

    success = await manager.set(user_id, "music_app", "spotify")
    prefs = await manager.get_preferences(user_id)

    assert success is True
    assert prefs.get("music_app") == "spotify"


@pytest.mark.asyncio
async def test_preference_manager_extract_from_text(tmp_path):
    manager = PreferenceManager(storage_path=str(tmp_path / "prefs"))
    user_id = "u-pref-2"

    await manager.extract_from_text("I use Firefox and I like lo-fi music", user_id)
    prefs = await manager.get_preferences(user_id)

    assert prefs.get("preferred_browser") == "firefox"
    assert prefs.get("music_genre") == "lo-fi music"


@pytest.mark.asyncio
async def test_preference_manager_missing_file_returns_empty(tmp_path):
    manager = PreferenceManager(storage_path=str(tmp_path / "prefs"))
    prefs = await manager.get_preferences("missing-user")
    assert prefs == {}


@pytest.mark.asyncio
async def test_preference_manager_corrupt_file_quarantined(tmp_path):
    manager = PreferenceManager(storage_path=str(tmp_path / "prefs"))
    user_id = "u-pref-corrupt"
    user_file = (tmp_path / "prefs") / f"{user_id}.json"
    user_file.write_text("{not-json", encoding="utf-8")

    prefs = await manager.get_preferences(user_id)
    assert prefs == {}
    assert not user_file.exists()
    corrupt_files = list((tmp_path / "prefs").glob(f"{user_id}.corrupt.*"))
    assert len(corrupt_files) == 1
