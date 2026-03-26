import asyncio
import logging
from logging import StreamHandler
from types import SimpleNamespace

import pytest

import agent


@pytest.mark.asyncio
async def test_worker_session_bootstrap_single_job(monkeypatch, caplog):
    agent._ACTIVE_JOB_BOOTSTRAPS.clear()
    entered = 0
    release = asyncio.Event()

    async def _fake_worker_session_impl(_ctx):
        nonlocal entered
        entered += 1
        await release.wait()

    monkeypatch.setattr(agent, "_handle_worker_session_impl", _fake_worker_session_impl)
    ctx = SimpleNamespace(job=SimpleNamespace(id="job-single-bootstrap"))

    with caplog.at_level(logging.ERROR):
        first = asyncio.create_task(agent._handle_worker_session(ctx))
        await asyncio.sleep(0.01)
        second = asyncio.create_task(agent._handle_worker_session(ctx))
        await asyncio.sleep(0.05)
        release.set()
        await asyncio.gather(first, second)

    assert entered == 1
    assert "job-single-bootstrap" not in agent._ACTIVE_JOB_BOOTSTRAPS


def test_normalize_worker_logging_dedupes_handlers():
    root = logging.getLogger()
    module_logger = logging.getLogger(agent.__name__)
    main_logger = logging.getLogger("__main__")
    mp_logger = logging.getLogger("__mp_main__")

    root_original_handlers = list(root.handlers)
    module_original_handlers = list(module_logger.handlers)
    main_original_handlers = list(main_logger.handlers)
    mp_original_handlers = list(mp_logger.handlers)
    module_original_propagate = module_logger.propagate
    main_original_propagate = main_logger.propagate
    mp_original_propagate = mp_logger.propagate

    try:
        root.handlers = [StreamHandler(), StreamHandler()]
        module_logger.handlers = [StreamHandler()]
        main_logger.handlers = [StreamHandler()]
        mp_logger.handlers = [StreamHandler()]

        agent._normalize_worker_logging()

        assert len(root.handlers) == 1
        assert module_logger.handlers == []
        assert main_logger.handlers == []
        assert mp_logger.handlers == []
        assert module_logger.propagate is True
        assert main_logger.propagate is True
        assert mp_logger.propagate is True
    finally:
        root.handlers = root_original_handlers
        module_logger.handlers = module_original_handlers
        main_logger.handlers = main_original_handlers
        mp_logger.handlers = mp_original_handlers
        module_logger.propagate = module_original_propagate
        main_logger.propagate = main_original_propagate
        mp_logger.propagate = mp_original_propagate
