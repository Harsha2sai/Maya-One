import datetime
from unittest.mock import patch

from core.utils.context_signal import get_music_query, get_time_context

REAL_DATETIME = datetime.datetime


def test_morning_mood():
    with patch("core.utils.context_signal.datetime.datetime") as mock_dt:
        mock_dt.now.return_value = REAL_DATETIME(2026, 4, 3, 7, 0)
        context = get_time_context()
    assert context["period"] == "morning"
    assert context["mood"] == "energetic"


def test_work_mood():
    with patch("core.utils.context_signal.datetime.datetime") as mock_dt:
        mock_dt.now.return_value = REAL_DATETIME(2026, 4, 3, 10, 0)
        context = get_time_context()
    assert context["mood"] == "focused"


def test_music_query_combines_genre_and_mood():
    with patch("core.utils.context_signal.datetime.datetime") as mock_dt:
        mock_dt.now.return_value = REAL_DATETIME(2026, 4, 3, 21, 0)
        query = get_music_query("lo-fi")
    assert query == "lo-fi sleep"
