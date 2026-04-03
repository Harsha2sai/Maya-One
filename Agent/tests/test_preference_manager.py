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
