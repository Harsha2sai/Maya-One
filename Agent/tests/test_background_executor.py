import asyncio

import pytest

from core.tasks.background import BackgroundExecutor, RecoveryManager, TaskScheduler


class _FakePersistence:
    def __init__(self):
        self.checkpoints = []
        self.terminals = []
        self.recovery_rows = []
        self.user_ids = []

    async def save_checkpoint(self, task_id, step_id, payload, checkpoint_id=None, ts=None):
        self.checkpoints.append(
            {
                "task_id": task_id,
                "step_id": step_id,
                "payload": payload,
                "checkpoint_id": checkpoint_id,
                "ts": ts,
            }
        )
        return checkpoint_id or f"chk_{len(self.checkpoints)}"

    async def mark_terminal(self, task_id, status, reason):
        self.terminals.append({"task_id": task_id, "status": status, "reason": reason})
        return True

    async def recover_background_tasks(self, user_id=None):
        self.user_ids.append(user_id)
        return list(self.recovery_rows)


@pytest.mark.asyncio
async def test_register_handler_requires_name_and_callable():
    executor = BackgroundExecutor()

    with pytest.raises(ValueError):
        executor.register_handler("", lambda payload: payload)

    with pytest.raises(TypeError):
        executor.register_handler("echo", "not-callable")


@pytest.mark.asyncio
async def test_submit_requires_task_id():
    executor = BackgroundExecutor()
    executor.register_handler("echo", lambda payload: payload)

    with pytest.raises(ValueError):
        await executor.submit(task_id="", task_type="echo", payload={})


@pytest.mark.asyncio
async def test_submit_requires_registered_task_type():
    executor = BackgroundExecutor()

    with pytest.raises(KeyError):
        await executor.submit(task_id="t1", task_type="missing", payload={})


@pytest.mark.asyncio
async def test_submit_sync_handler_completes():
    executor = BackgroundExecutor()
    executor.register_handler("echo", lambda payload: {"echo": payload.get("value")})

    started = await executor.submit(task_id="t1", task_type="echo", payload={"value": 7})
    done = await executor.await_completion(started["task_ref"], timeout=1.0)

    assert done["status"] == "completed"
    assert done["result"] == {"echo": 7}


@pytest.mark.asyncio
async def test_submit_async_handler_completes():
    executor = BackgroundExecutor()

    async def _handler(payload):
        await asyncio.sleep(0.01)
        return {"ok": payload.get("ok")}

    executor.register_handler("async", _handler)
    started = await executor.submit(task_id="t2", task_type="async", payload={"ok": True})
    done = await executor.await_completion(started["task_ref"], timeout=1.0)

    assert done["status"] == "completed"
    assert done["result"] == {"ok": True}


@pytest.mark.asyncio
async def test_submit_handler_error_marks_failed():
    executor = BackgroundExecutor()

    def _handler(_payload):
        raise RuntimeError("boom")

    executor.register_handler("explode", _handler)
    started = await executor.submit(task_id="t3", task_type="explode", payload={})
    done = await executor.await_completion(started["task_ref"], timeout=1.0)

    assert done["status"] == "failed"
    assert "boom" in str(done["error"])


@pytest.mark.asyncio
async def test_cancel_running_task_marks_cancelled():
    executor = BackgroundExecutor()

    async def _slow(_payload):
        await asyncio.sleep(1.0)
        return {"ok": True}

    executor.register_handler("slow", _slow)
    started = await executor.submit(task_id="t4", task_type="slow", payload={})
    cancelled = await executor.cancel(started["task_ref"])

    assert cancelled["status"] == "cancelled"


@pytest.mark.asyncio
async def test_await_completion_timeout_raises():
    executor = BackgroundExecutor()

    async def _slow(_payload):
        await asyncio.sleep(0.2)
        return {"ok": True}

    executor.register_handler("slow", _slow)
    started = await executor.submit(task_id="t5", task_type="slow", payload={})

    with pytest.raises(TimeoutError):
        await executor.await_completion(started["task_ref"], timeout=0.01)


@pytest.mark.asyncio
async def test_get_status_missing_task_raises():
    executor = BackgroundExecutor()

    with pytest.raises(LookupError):
        await executor.get_status("missing")


@pytest.mark.asyncio
async def test_resume_task_restarts_from_metadata_payload():
    executor = BackgroundExecutor()
    executor.register_handler("echo", lambda payload: {"echo": payload.get("value")})

    resumed = await executor.resume_task(
        {
            "task_id": "t6",
            "status": "RUNNING",
            "metadata": {
                "task_type": "echo",
                "payload": {"value": 11},
                "recoverable": True,
            },
        }
    )

    assert resumed is not None
    done = await executor.await_completion(resumed["task_ref"], timeout=1.0)
    assert done["status"] == "completed"
    assert done["result"] == {"echo": 11}


@pytest.mark.asyncio
async def test_resume_task_skips_terminal_rows():
    executor = BackgroundExecutor()
    executor.register_handler("echo", lambda payload: payload)

    resumed = await executor.resume_task(
        {
            "task_id": "t7",
            "status": "COMPLETED",
            "metadata": {"task_type": "echo", "payload": {}},
        }
    )

    assert resumed is None


@pytest.mark.asyncio
async def test_shutdown_cancels_running_tasks():
    executor = BackgroundExecutor()

    async def _slow(_payload):
        await asyncio.sleep(1.0)
        return {"ok": True}

    executor.register_handler("slow", _slow)
    started = await executor.submit(task_id="t8", task_type="slow", payload={})

    await executor.shutdown(cancel_running=True)
    status = await executor.get_status(started["task_ref"])
    assert status["status"] in {"cancelled", "completed"}


@pytest.mark.asyncio
async def test_persistence_receives_checkpoints_and_terminal_markers():
    persistence = _FakePersistence()
    executor = BackgroundExecutor(persistence=persistence)
    executor.register_handler("echo", lambda payload: payload)

    started = await executor.submit(task_id="t9", task_type="echo", payload={"x": 1})
    done = await executor.await_completion(started["task_ref"], timeout=1.0)

    assert done["status"] == "completed"
    assert len(persistence.checkpoints) >= 2
    assert persistence.checkpoints[0]["payload"]["event"] == "background_submitted"
    assert persistence.checkpoints[-1]["payload"]["event"] == "background_completed"
    assert persistence.terminals[-1]["status"] == "COMPLETED"


def test_scheduler_rejects_invalid_cron_expression():
    executor = BackgroundExecutor()
    scheduler = TaskScheduler(executor=executor)

    with pytest.raises(ValueError):
        scheduler.add_cron_task(
            job_id="job1",
            task_id="t10",
            task_type="echo",
            cron_expression="* * *",
        )


@pytest.mark.asyncio
async def test_scheduler_add_list_remove_job():
    executor = BackgroundExecutor()
    scheduler = TaskScheduler(executor=executor)

    job = scheduler.add_cron_task(
        job_id="job2",
        task_id="t11",
        task_type="echo",
        cron_expression="*/5 * * * *",
        payload={"a": 1},
    )

    listed = scheduler.list_tasks()
    removed = scheduler.remove_task("job2")

    assert job.job_id == "job2"
    assert len(listed) == 1
    assert listed[0]["payload"] == {"a": 1}
    assert removed is True


@pytest.mark.asyncio
async def test_scheduler_run_due_job_dispatches_executor():
    executor = BackgroundExecutor()
    executor.register_handler("echo", lambda payload: {"echo": payload.get("msg")})
    scheduler = TaskScheduler(executor=executor)

    scheduler.add_cron_task(
        job_id="job3",
        task_id="t12",
        task_type="echo",
        cron_expression="0 * * * *",
        payload={"msg": "hello"},
    )

    started = await scheduler.run_due_job("job3")
    done = await executor.await_completion(started["task_ref"], timeout=1.0)

    assert done["status"] == "completed"
    assert done["result"] == {"echo": "hello"}


@pytest.mark.asyncio
async def test_scheduler_start_shutdown_are_idempotent():
    executor = BackgroundExecutor()
    scheduler = TaskScheduler(executor=executor)

    await scheduler.start()
    await scheduler.start()
    assert scheduler.started is True

    await scheduler.shutdown()
    await scheduler.shutdown()
    assert scheduler.started is False


@pytest.mark.asyncio
async def test_recovery_manager_resumes_recoverable_rows():
    persistence = _FakePersistence()
    persistence.recovery_rows = [
        {
            "task_id": "t13",
            "status": "RUNNING",
            "metadata": {"task_type": "echo", "payload": {"v": 3}},
        },
        {
            "task_id": "t14",
            "status": "COMPLETED",
            "metadata": {"task_type": "echo", "payload": {"v": 4}},
        },
    ]

    executor = BackgroundExecutor(persistence=persistence)
    executor.register_handler("echo", lambda payload: {"v": payload.get("v")})
    manager = RecoveryManager(persistence=persistence, executor=executor)

    resumed = await manager.recover(user_id="u1")
    assert len(resumed) == 1

    done = await executor.await_completion(resumed[0]["task_ref"], timeout=1.0)
    assert done["result"] == {"v": 3}


@pytest.mark.asyncio
async def test_recovery_manager_uses_default_user_id_when_not_provided():
    persistence = _FakePersistence()
    persistence.recovery_rows = []

    executor = BackgroundExecutor(persistence=persistence)
    manager = RecoveryManager(persistence=persistence, executor=executor, user_id="user-default")

    resumed = await manager.recover()
    assert resumed == []
    assert persistence.user_ids[-1] == "user-default"
