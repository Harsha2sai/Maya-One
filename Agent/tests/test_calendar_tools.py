from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlite3
from uuid import uuid4

from tools import storage


def _context(user_id: str = "calendar-user"):
    return SimpleNamespace(job_context=SimpleNamespace(user_id=user_id))


async def _create_event(context, **kwargs):
    return await storage.create_calendar_event.__wrapped__(context, **kwargs)


async def _list_events(context):
    return await storage.list_calendar_events.__wrapped__(context)


async def _delete_event(context, event_id: str):
    return await storage.delete_calendar_event.__wrapped__(context, event_id)


@pytest_asyncio.fixture
async def calendar_db(monkeypatch):
    db_key = f"file:calendar_tools_test_{uuid4().hex}?mode=memory&cache=shared"
    monkeypatch.setattr(storage, "_get_db_path", lambda: db_key)

    anchor = sqlite3.connect(db_key, uri=True)
    await storage._ensure_calendar_events_table(db_key)
    try:
        yield db_key
    finally:
        anchor.close()


@pytest.mark.asyncio
async def test_create_calendar_event_returns_confirmation(calendar_db):
    result = await _create_event(
        _context(),
        title="Team Meeting",
        start_time="tomorrow at 2pm",
        end_time="tomorrow at 3pm",
        description="Sprint sync",
    )
    assert "Created calendar event 'Team Meeting'" in result


@pytest.mark.asyncio
async def test_list_calendar_events_empty_returns_no_events(calendar_db):
    result = await _list_events(_context())
    assert result == "No upcoming calendar events."


@pytest.mark.asyncio
async def test_list_calendar_events_returns_created_event(calendar_db):
    await storage._create_calendar_event_record(
        db_path=calendar_db,
        user_id="calendar-user",
        title="Architecture Review",
        start_time="2026-03-24 14:00",
        end_time="2026-03-24 15:00",
        description="Phase 10 prep",
    )

    result = await _list_events(_context())
    assert "Upcoming events:" in result
    assert "Architecture Review: 2026-03-24 14:00 to 2026-03-24 15:00" in result
    assert "(Phase 10 prep)" in result


@pytest.mark.asyncio
async def test_delete_calendar_event_removes_it(calendar_db):
    event_id = await storage._create_calendar_event_record(
        db_path=calendar_db,
        user_id="calendar-user",
        title="Delete Me",
        start_time="2026-03-24 10:00",
        end_time="2026-03-24 11:00",
    )

    result = await _delete_event(_context(), event_id)
    assert result == f"Deleted calendar event {event_id}."

    listed = await _list_events(_context())
    assert listed == "No upcoming calendar events."


@pytest.mark.asyncio
async def test_delete_nonexistent_event_returns_not_found(calendar_db):
    result = await _delete_event(_context(), "missing-id")
    assert result == "No calendar event found with ID missing-id."


@pytest.mark.asyncio
async def test_create_and_list_multiple_events(calendar_db):
    await storage._create_calendar_event_record(
        db_path=calendar_db,
        user_id="calendar-user",
        title="Event B",
        start_time="2026-03-25 12:00",
        end_time="2026-03-25 13:00",
    )
    await storage._create_calendar_event_record(
        db_path=calendar_db,
        user_id="calendar-user",
        title="Event A",
        start_time="2026-03-24 09:00",
        end_time="2026-03-24 10:00",
        description="Earlier event",
    )

    result = await _list_events(_context())
    first = result.index("Event A")
    second = result.index("Event B")
    assert first < second
