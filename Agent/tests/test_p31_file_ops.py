"""Tests for P31 Tier 1 file operation tools."""

import pytest
from pathlib import Path
from core.tools.file_ops import file_read, file_write, file_edit, file_glob, file_grep


# ── file_read ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_read_full(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\n")
    result = await file_read(str(f))
    assert "line1" in result
    assert "line3" in result


@pytest.mark.asyncio
async def test_file_read_with_offset_and_limit(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("a\nb\nc\nd\ne\n")
    result = await file_read(str(f), offset=2, limit=2)
    assert "b" in result
    assert "c" in result
    assert "d" not in result


@pytest.mark.asyncio
async def test_file_read_missing_file():
    result = await file_read("/nonexistent/path/file.txt")
    assert result.startswith("Error:")


# ── file_write ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_write_creates_file(tmp_path):
    f = tmp_path / "out.txt"
    result = await file_write(str(f), "hello world")
    assert "OK" in result
    assert f.read_text() == "hello world"


@pytest.mark.asyncio
async def test_file_write_append(tmp_path):
    f = tmp_path / "out.txt"
    f.write_text("first\n")
    await file_write(str(f), "second\n", append=True)
    assert f.read_text() == "first\nsecond\n"


@pytest.mark.asyncio
async def test_file_write_creates_parent_dirs(tmp_path):
    f = tmp_path / "deep" / "nested" / "file.txt"
    result = await file_write(str(f), "content")
    assert "OK" in result
    assert f.exists()


# ── file_edit ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_edit_replaces_first_occurrence(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("foo = 1\nfoo = 2\n")
    result = await file_edit(str(f), "foo = 1", "bar = 1")
    assert "OK" in result
    assert f.read_text() == "bar = 1\nfoo = 2\n"


@pytest.mark.asyncio
async def test_file_edit_replace_all(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("x\nx\nx\n")
    result = await file_edit(str(f), "x", "y", replace_all=True)
    assert "3 replacement" in result
    assert f.read_text() == "y\ny\ny\n"


@pytest.mark.asyncio
async def test_file_edit_old_string_not_found(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("hello\n")
    result = await file_edit(str(f), "missing_string", "replacement")
    assert result.startswith("Error:")


@pytest.mark.asyncio
async def test_file_edit_missing_file():
    result = await file_edit("/no/such/file.py", "old", "new")
    assert result.startswith("Error:")


# ── file_glob ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_glob_finds_files(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "c.txt").write_text("")
    result = await file_glob("*.py", str(tmp_path))
    assert "a.py" in result
    assert "b.py" in result
    assert "c.txt" not in result


@pytest.mark.asyncio
async def test_file_glob_no_matches(tmp_path):
    result = await file_glob("*.xyz", str(tmp_path))
    assert "No files matched" in result


@pytest.mark.asyncio
async def test_file_glob_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.py").write_text("")
    result = await file_glob("**/*.py", str(tmp_path))
    assert "deep.py" in result


# ── file_grep ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_grep_finds_pattern(tmp_path):
    f = tmp_path / "src.py"
    f.write_text("def hello():\n    pass\n")
    result = await file_grep("def hello", str(tmp_path))
    assert "src.py" in result


@pytest.mark.asyncio
async def test_file_grep_no_match(tmp_path):
    f = tmp_path / "src.py"
    f.write_text("nothing here\n")
    result = await file_grep("xyz_not_present", str(tmp_path))
    assert "No matches" in result


@pytest.mark.asyncio
async def test_file_grep_content_mode(tmp_path):
    f = tmp_path / "src.py"
    f.write_text("alpha\nbeta\ngamma\n")
    result = await file_grep("beta", str(tmp_path), output_mode="content")
    assert "beta" in result
