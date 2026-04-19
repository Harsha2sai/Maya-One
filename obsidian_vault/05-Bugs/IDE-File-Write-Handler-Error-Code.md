# Bug: IDE File Write Handler — IsADirectoryError Returns 500

**Detected:** 2026-04-19
**Status:** 🔴 OPEN — Medium
**File:** `Agent/api/handlers.py`
**Function:** `handle_ide_file_write`

## Description
The `handle_ide_file_write` handler only catches `SessionNotFoundError` and `PathEscapeError`. If the caller passes a path that resolves to a directory (e.g., `relative_path="somefile/"` instead of `"somefile"`), `target.write_text()` raises `IsADirectoryError`. This exception falls through to the bare `except Exception` at line 445, which returns a **500 Internal Server Error** instead of a **400 Bad Request**.

## Location
```python
# handlers.py (approximate lines 445-453)
try:
    file_service.write_file(...)  # raises IsADirectoryError on dir path
except SessionNotFoundError:
    return JSONResponse(status_code=404, ...)
except PathEscapeError:
    return JSONResponse(status_code=400, ...)
except Exception:  # ← IsADirectoryError lands here → 500
    logger.exception(...)
    return JSONResponse(status_code=500, ...)
```

## Expected Behavior
- `IsADirectoryError` → `400 Bad Request` with message indicating path is a directory
- `NotADirectoryError` → `400 Bad Request`
- Generic `Exception` → `500 Internal Server Error` (already has bare except)

## Impact
- Client receives a 500 error for what is clearly a client-input error (bad path format)
- Logs show `IsADirectoryError` as a logged exception even though it's a 4xx class issue
- Confusing for API consumers debugging path issues

## Recommended Fix
```python
except (SessionNotFoundError, PathEscapeError):
    ...
except IsADirectoryError:
    return JSONResponse(status_code=400, body={"error": "Cannot write to a directory path"})
except NotADirectoryError:
    return JSONResponse(status_code=400, body={"error": "Part of path is not a directory"})
except Exception:
    logger.exception(...)
    return JSONResponse(status_code=500, ...)
```

## Related
- [[2026-04-19]] — Bug found during vault audit
- `core/ide/ide_file_service.py` — File service (correct behavior) — issue is in the handler wrapper only

## Verification
Run: `python3 -m pytest tests/test_ide_runtime.py tests/test_api_handlers.py -q -k ide`