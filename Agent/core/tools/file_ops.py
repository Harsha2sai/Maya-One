"""
P31 Tier 1 — File operation tools.
Read, Write, Edit, Glob, Grep.

All tools are plain async callables compatible with ToolManager.
"""

from __future__ import annotations

import glob as _glob
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def file_read(
    file_path: str,
    offset: int = 1,
    limit: Optional[int] = None,
) -> str:
    """Read a file, optionally restricted to a line range.

    Args:
        file_path: Absolute or relative path to the file.
        offset: 1-based line number to start reading from (default: 1).
        limit: Maximum number of lines to return (default: all).

    Returns:
        File content as a string, or an error message.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: file not found: {file_path}"
        if not path.is_file():
            return f"Error: not a file: {file_path}"

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        start = max(0, offset - 1)
        end = start + limit if limit else len(lines)
        selected = lines[start:end]

        return "".join(selected)
    except Exception as e:
        logger.error("file_read error path=%s: %s", file_path, e)
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

async def file_write(
    file_path: str,
    content: str,
    append: bool = False,
) -> str:
    """Create or overwrite a file with the given content.

    Args:
        file_path: Path to write to. Parent directories are created if needed.
        content: Text content to write.
        append: If True, append to existing file instead of overwriting.

    Returns:
        Success message or error string.
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as f:
            f.write(content)

        action = "appended" if append else "written"
        logger.info("file_write %s path=%s bytes=%d", action, file_path, len(content))
        return f"OK: {len(content)} bytes {action} to {file_path}"
    except Exception as e:
        logger.error("file_write error path=%s: %s", file_path, e)
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Edit  (exact string replacement)
# ---------------------------------------------------------------------------

async def file_edit(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Replace an exact string in a file.

    Args:
        file_path: Path to the file to edit.
        old_string: Exact text to find and replace.
        new_string: Replacement text.
        replace_all: If True, replace every occurrence; otherwise only the first.

    Returns:
        Success message with replacement count, or error string.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: file not found: {file_path}"

        content = path.read_text(encoding="utf-8", errors="replace")

        if old_string not in content:
            return f"Error: old_string not found in {file_path}"

        if replace_all:
            new_content = content.replace(old_string, new_string)
            count = content.count(old_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
            count = 1

        path.write_text(new_content, encoding="utf-8")
        logger.info("file_edit path=%s replacements=%d", file_path, count)
        return f"OK: {count} replacement(s) in {file_path}"
    except Exception as e:
        logger.error("file_edit error path=%s: %s", file_path, e)
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Glob  (pattern file matching)
# ---------------------------------------------------------------------------

async def file_glob(
    pattern: str,
    path: str = ".",
) -> str:
    """Find files matching a glob pattern.

    Args:
        pattern: Glob pattern, e.g. ``**/*.py`` or ``src/*.ts``.
        path: Base directory to search from (default: current directory).

    Returns:
        Newline-separated list of matching paths, or an error string.
    """
    try:
        base = Path(path).resolve()
        if not base.exists():
            return f"Error: base path not found: {path}"

        matches = sorted(_glob.glob(pattern, root_dir=str(base), recursive=True))

        if not matches:
            return f"No files matched pattern '{pattern}' in {path}"

        return "\n".join(matches)
    except Exception as e:
        logger.error("file_glob error pattern=%s path=%s: %s", pattern, path, e)
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Grep  (content search via ripgrep with fallback to Python re)
# ---------------------------------------------------------------------------

async def file_grep(
    pattern: str,
    path: str = ".",
    glob_filter: Optional[str] = None,
    output_mode: str = "files",
    context_lines: int = 0,
) -> str:
    """Search file contents for a regex pattern.

    Uses ripgrep (``rg``) when available, falls back to Python ``re``.

    Args:
        pattern: Regex pattern to search for.
        path: Directory or file to search.
        glob_filter: Optional file pattern filter, e.g. ``*.py``.
        output_mode: ``"files"`` (filenames only), ``"content"`` (matching lines),
            or ``"count"`` (match count per file).
        context_lines: Lines of context around each match (content mode only).

    Returns:
        Search results as a string, or an error string.
    """
    try:
        # Try ripgrep first
        cmd = ["rg", "--no-heading", pattern]

        if output_mode == "files":
            cmd.append("-l")
        elif output_mode == "count":
            cmd.append("-c")

        if glob_filter:
            cmd.extend(["-g", glob_filter])

        if context_lines > 0 and output_mode == "content":
            cmd.extend(["-C", str(context_lines)])

        cmd.append(path)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            output = result.stdout.strip()
            return output if output else f"No matches for '{pattern}' in {path}"
        elif result.returncode == 1:
            return f"No matches for '{pattern}' in {path}"
        else:
            raise RuntimeError(result.stderr.strip())

    except FileNotFoundError:
        # ripgrep not available — fall back to Python re
        return await _python_grep(pattern, path, glob_filter, output_mode, context_lines)
    except subprocess.TimeoutExpired:
        return "Error: grep timed out after 30 seconds"
    except Exception as e:
        logger.error("file_grep error pattern=%s path=%s: %s", pattern, path, e)
        return f"Error: {e}"


async def _python_grep(
    pattern: str,
    path: str,
    glob_filter: Optional[str],
    output_mode: str,
    context_lines: int,
) -> str:
    """Pure-Python grep fallback when ripgrep is unavailable."""
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex: {e}"

    base = Path(path)
    search_glob = glob_filter or "**/*"
    candidates = (
        [base] if base.is_file()
        else [p for p in base.glob(search_glob) if p.is_file()]
    )

    results: list[str] = []
    for file_path in sorted(candidates):
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            matching = [i for i, ln in enumerate(lines) if compiled.search(ln)]

            if not matching:
                continue

            if output_mode == "files":
                results.append(str(file_path))
            elif output_mode == "count":
                results.append(f"{file_path}:{len(matching)}")
            else:
                for idx in matching:
                    start = max(0, idx - context_lines)
                    end = min(len(lines), idx + context_lines + 1)
                    for ln_idx in range(start, end):
                        prefix = ">" if ln_idx == idx else " "
                        results.append(f"{file_path}:{ln_idx + 1}{prefix} {lines[ln_idx]}")
        except Exception:
            continue

    return "\n".join(results) if results else f"No matches for '{pattern}' in {path}"
