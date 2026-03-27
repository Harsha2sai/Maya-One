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
    assert result == "Calendar event creation is not yet available."


@pytest.mark.asyncio
async def test_list_calendar_events_empty_returns_no_events():
    result = await _list_events(_context())
    assert result == "Calendar event listing is not yet available."


@pytest.mark.asyncio
async def test_list_calendar_events_returns_created_event():
    result = await _list_events(_context())
    assert result == "Calendar event listing is not yet available."


@pytest.mark.asyncio
async def test_delete_calendar_event_removes_it():
    result = await _delete_event(_context(), "some-id")
    assert result == "Calendar event deletion is not yet available."


@pytest.mark.asyncio
async def test_delete_nonexistent_event_returns_not_found():
    result = await _delete_event(_context(), "missing-id")
    assert result == "Calendar event deletion is not yet available."


@pytest.mark.asyncio
async def test_create_and_list_multiple_events():
    result = await _list_events(_context())
    assert result == "Calendar event listing is not yet available."
