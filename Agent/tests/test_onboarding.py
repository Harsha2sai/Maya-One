"""Tests for first-run onboarding logic."""
import pytest
from core.orchestrator.onboarding import (
    is_onboarding_complete,
    extract_onboarding_prefs,
    build_onboarding_system_note,
    ONBOARDING_KEYS,
)


def test_onboarding_complete_with_all_keys():
    prefs = {"music_app": "spotify", "home_city": "Hyderabad"}
    assert is_onboarding_complete(prefs) is True


def test_onboarding_incomplete_missing_city():
    prefs = {"music_app": "spotify"}
    assert is_onboarding_complete(prefs) is False


def test_onboarding_incomplete_empty_prefs():
    assert is_onboarding_complete({}) is False


def test_onboarding_incomplete_empty_values():
    prefs = {"music_app": "", "home_city": ""}
    assert is_onboarding_complete(prefs) is False


def test_extract_spotify():
    result = extract_onboarding_prefs("I use Spotify for music")
    assert result.get("music_app") == "spotify"


def test_extract_youtube_music():
    result = extract_onboarding_prefs("I prefer YouTube Music")
    assert result.get("music_app") == "youtube music"


def test_extract_city():
    result = extract_onboarding_prefs("I'm based in Hyderabad")
    assert result.get("home_city") == "Hyderabad"


def test_extract_city_from_in():
    result = extract_onboarding_prefs("I am in Mumbai")
    assert result.get("home_city") == "Mumbai"


def test_extract_both():
    result = extract_onboarding_prefs(
        "I use Spotify and I'm based in Bangalore"
    )
    assert result.get("music_app") == "spotify"
    assert result.get("home_city") == "Bangalore"


def test_extract_no_match():
    result = extract_onboarding_prefs("what time is it")
    assert result == {}


def test_system_note_content():
    note = build_onboarding_system_note()
    assert "ONBOARDING" in note
    assert "music app" in note
    assert "city" in note
