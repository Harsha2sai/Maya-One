import os
import sys
import asyncio

import pytest_asyncio

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_leaked_asyncio_tasks():
    yield
    current = asyncio.current_task()

    def _is_anyio_runner_task(task: asyncio.Task) -> bool:
        coro = task.get_coro()
        qualname = getattr(coro, "__qualname__", "")
        code = getattr(coro, "cr_code", None)
        code_name = getattr(code, "co_name", "")
        markers = {
            "_call_in_runner_task",
            "_run_tests_and_fixtures",
            "run_asyncgen_fixture",
        }
        text = f"{qualname} {code_name}"
        return any(marker in text for marker in markers)

    pending = [
        task
        for task in asyncio.all_tasks()
        if task is not current and not task.done() and not _is_anyio_runner_task(task)
    ]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
