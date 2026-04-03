import re
import pytest
import pytest_asyncio
from types import SimpleNamespace

from tools import storage


def _context(user_id: str = "calendar-user"):
    return SimpleNamespace(job_context=SimpleNamespace(user_id=user_id))


async def _create_event(context, **kwargs):
    return await storage.create_calendar_event.__wrapped__(context, **kwargs)


async def _list_events(context):
    return await storage.list_calendar_events.__wrapped__(context)


async def _delete_event(context, event_id: str):
    return await storage.delete_calendar_event.__wrapped__(context, event_id)


@pytest.mark.asyncio
async def test_create_calendar_event_returns_confirmation():
    result = await _create_event(
        _context(),
        title="Team Meeting",
        start_time="tomorrow at 2pm",
        end_time="tomorrow at 3pm",
        description="Sprint sync",
    )
    assert "Created calendar event" in result


@pytest.mark.asyncio
async def test_list_calendar_events_empty_returns_no_events():
    result = await _list_events(_context(user_id="calendar-user-empty"))
    assert (
        "No upcoming events" in result
        or "no upcoming calendar events" in result.lower()
        or "no events" in result.lower()
    )


@pytest.mark.asyncio
async def test_list_calendar_events_returns_created_event():
    context = _context(user_id="calendar-user-with-event")
    created = await _create_event(
        context,
        title="Team Meeting",
        start_time="tomorrow at 2pm",
        end_time="tomorrow at 3pm",
        description="Sprint sync",
    )
    assert "Created calendar event" in created
    result = await _list_events(context)
    assert "Upcoming events" in result


@pytest.mark.asyncio
async def test_delete_calendar_event_removes_it():
    context = _context(user_id="calendar-user-delete")
    created = await _create_event(
        context,
        title="Delete Me",
        start_time="tomorrow at 4pm",
        end_time="tomorrow at 5pm",
        description="Cleanup",
    )
    assert "Created calendar event" in created
    match = re.search(r"ID:\s*([^)]+)\)", created)
    event_id = match.group(1) if match else "some-id"
    result = await _delete_event(context, event_id)
    assert "Deleted" in result or "removed" in result.lower()


@pytest.mark.asyncio
async def test_delete_nonexistent_event_returns_not_found():
    result = await _delete_event(_context(), "missing-id")
    assert "No calendar event found" in result or "not found" in result.lower()


@pytest.mark.asyncio
async def test_create_and_list_multiple_events():
    context = _context()
    created_first = await _create_event(
        context,
        title="Daily Standup",
        start_time="tomorrow at 9am",
        end_time="tomorrow at 9:15am",
        description="Team sync",
    )
    assert "Created calendar event" in created_first
    created_second = await _create_event(
        context,
        title="Planning Session",
        start_time="tomorrow at 10am",
        end_time="tomorrow at 11am",
        description="Roadmap planning",
    )
    assert "Created calendar event" in created_second
    result = await _list_events(context)
    assert "Upcoming events" in result
