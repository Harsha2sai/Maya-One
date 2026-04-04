from types import SimpleNamespace
import importlib

import pytest
import pytest_asyncio
import sqlite3
from uuid import uuid4

from tools import storage as storage_module

storage = importlib.reload(storage_module)

_CREATE_NOTE = getattr(storage.create_note, "__wrapped__", storage.create_note)
_LIST_NOTES = getattr(storage.list_notes, "__wrapped__", storage.list_notes)
_READ_NOTE = getattr(storage.read_note, "__wrapped__", storage.read_note)
_DELETE_NOTE = getattr(storage.delete_note, "__wrapped__", storage.delete_note)


def _context(user_id: str = "note-user"):
    return SimpleNamespace(job_context=SimpleNamespace(user_id=user_id))


async def _create_note(context, **kwargs):
    return await _CREATE_NOTE(context, **kwargs)


async def _list_notes(context):
    return await _LIST_NOTES(context)


async def _read_note(context, title: str):
    return await _READ_NOTE(context, title)


async def _delete_note(context, title: str):
    return await _DELETE_NOTE(context, title)


@pytest_asyncio.fixture
async def notes_db(monkeypatch):
    db_key = f"file:note_tools_test_{uuid4().hex}?mode=memory&cache=shared"
    monkeypatch.setattr(storage, "_get_db_path", lambda: db_key)

    anchor = sqlite3.connect(db_key, uri=True)
    await storage._ensure_notes_table(db_key)
    try:
        yield db_key
    finally:
        anchor.close()


@pytest.mark.asyncio
async def test_create_note_returns_confirmation(notes_db):
    result = await _create_note(_context(), title="Sprint Ideas", content="Build note parity.")
    assert result == "Note 'Sprint Ideas' created."


@pytest.mark.asyncio
async def test_list_notes_empty_returns_no_notes(notes_db):
    result = await _list_notes(_context())
    assert result == "You have no notes."


@pytest.mark.asyncio
async def test_list_notes_returns_created_note(notes_db):
    await storage._create_note_record(notes_db, "note-user", "Architecture", "Phase 9E details go here.")

    result = await _list_notes(_context())
    assert "Recent Notes:" in result
    assert "- Architecture: Phase 9E details go here." in result


@pytest.mark.asyncio
async def test_read_note_returns_single_exact_match(notes_db):
    await storage._create_note_record(notes_db, "note-user", "Sprint Ideas", "Ship note SQLite parity.")

    result = await _read_note(_context(), "Sprint Ideas")
    assert result == "Note 'Sprint Ideas': Ship note SQLite parity."


@pytest.mark.asyncio
async def test_read_note_missing_returns_not_found(notes_db):
    result = await _read_note(_context(), "Missing")
    assert result == "No note found with title 'Missing'."


@pytest.mark.asyncio
async def test_read_note_duplicate_title_returns_needs_followup(notes_db):
    await storage._create_note_record(notes_db, "note-user", "Daily", "Morning notes")
    await storage._create_note_record(notes_db, "note-user", "Daily", "Evening notes")

    result = await _read_note(_context(), "Daily")
    assert result == "needs_followup: Found multiple notes titled 'Daily'. Please specify which one."


@pytest.mark.asyncio
async def test_delete_note_removes_single_exact_match(notes_db):
    await storage._create_note_record(notes_db, "note-user", "Sprint Ideas", "Delete me")

    result = await _delete_note(_context(), "Sprint Ideas")
    assert result == "Deleted note 'Sprint Ideas'."
    assert await _read_note(_context(), "Sprint Ideas") == "No note found with title 'Sprint Ideas'."


@pytest.mark.asyncio
async def test_delete_note_duplicate_title_returns_needs_followup(notes_db):
    await storage._create_note_record(notes_db, "note-user", "Daily", "Morning notes")
    await storage._create_note_record(notes_db, "note-user", "Daily", "Evening notes")

    result = await _delete_note(_context(), "Daily")
    assert result == "needs_followup: Found multiple notes titled 'Daily'. Please specify which one."
