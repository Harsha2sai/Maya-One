import json
from datetime import datetime, timedelta, timezone

import pytest

from core.agents.base import AgentContext
from core.agents.contracts import AgentHandoffRequest, HandoffSignal
from core.agents.handoff_manager import HandoffManager
from core.agents.monitoring_agent import MonitoringAgent
from core.agents.registry import AgentRegistry


class _FakeSessionMonitor:
    def __init__(self, memory_mb: float = 128.0):
        self._memory_mb = float(memory_mb)

    def get_memory_usage(self) -> float:
        return self._memory_mb


def _context(**custom_data):
    return AgentContext(
        user_id="u1",
        user_role="USER",
        conversation_history=[],
        memory_context="",
        custom_data=custom_data,
    )


def _request(**overrides) -> AgentHandoffRequest:
    payload = {
        "handoff_id": "handoff-monitoring-1",
        "trace_id": "trace-monitoring-1",
        "conversation_id": "conversation-monitoring-1",
        "task_id": "task-monitoring-1",
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "monitoring",
        "intent": "monitoring",
        "user_text": "run a health check",
        "context_slice": "User requested monitoring info.",
        "execution_mode": "planning",
        "delegation_depth": 0,
        "max_depth": 1,
        "handoff_reason": "monitoring_test",
        "metadata": {"user_id": "u1", "operation": "health_check"},
    }
    payload.update(overrides)
    return AgentHandoffRequest(**payload)


@pytest.mark.asyncio
async def test_health_check_returns_snapshot_and_stable_status():
    agent = MonitoringAgent(session_monitor=_FakeSessionMonitor(memory_mb=256.0))
    agent._active_threads = lambda: 12
    agent._get_open_fds = lambda: 100

    status = await agent.health_check()

    assert status.status == "ok"
    assert status.healthy is True
    assert status.memory_mb == 256.0
    assert status.threads == 12
    assert status.open_fds == 100
    assert "threshold_checks" in status.checks
    assert "dependency_parity" in status.checks
    assert status.timestamp


@pytest.mark.asyncio
async def test_check_logs_filters_by_pattern_and_since_and_missing_is_safe(tmp_path):
    now = datetime.now(timezone.utc)
    older = (now - timedelta(minutes=10)).isoformat()
    recent = (now - timedelta(seconds=10)).isoformat()
    log_path = tmp_path / "agent.log"
    log_path.write_text(
        f"{older} ERROR core.old old failure\n"
        f"{recent} ERROR core.new recent failure\n"
        f"{recent} INFO core.new steady state\n",
        encoding="utf-8",
    )

    agent = MonitoringAgent(log_path=str(log_path), session_monitor=_FakeSessionMonitor())
    entries = await agent.check_logs("error", timedelta(minutes=1))

    assert len(entries) == 1
    assert entries[0].level == "ERROR"
    assert "recent failure" in entries[0].message

    missing = MonitoringAgent(log_path=str(tmp_path / "missing.log"), session_monitor=_FakeSessionMonitor())
    assert await missing.check_logs("error", timedelta(minutes=5)) == []


@pytest.mark.asyncio
async def test_export_metrics_prometheus_emits_expected_lines(tmp_path):
    metrics_path = tmp_path / "runtime_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "tasks_created_total": 2,
                "task_runtime_seconds": [1.0, 2.0],
            }
        ),
        encoding="utf-8",
    )

    agent = MonitoringAgent(metrics_path=str(metrics_path), session_monitor=_FakeSessionMonitor())
    output = await agent.export_metrics("prometheus")

    assert "maya_runtime_tasks_created_total 2.0" in output
    assert "maya_runtime_task_runtime_seconds_count 2" in output
    assert "maya_runtime_task_runtime_seconds_sum 3.0" in output
    assert "maya_runtime_task_runtime_seconds_avg 1.5" in output


@pytest.mark.asyncio
async def test_export_metrics_rejects_unsupported_format(tmp_path):
    metrics_path = tmp_path / "runtime_metrics.json"
    metrics_path.write_text("{}", encoding="utf-8")
    agent = MonitoringAgent(metrics_path=str(metrics_path), session_monitor=_FakeSessionMonitor())

    with pytest.raises(ValueError, match="unsupported metrics format"):
        await agent.export_metrics("json")


@pytest.mark.asyncio
async def test_set_alert_threshold_affects_health_classification():
    agent = MonitoringAgent(session_monitor=_FakeSessionMonitor(memory_mb=2500.0))
    agent._active_threads = lambda: 8
    agent._get_open_fds = lambda: 50

    baseline = await agent.health_check()
    assert baseline.status == "degraded"
    assert baseline.checks["threshold_checks"]["memory_mb"] == "breach"

    await agent.set_alert_threshold("memory_mb", 3000.0)
    updated = await agent.health_check()
    assert updated.status == "ok"
    assert updated.checks["threshold_checks"]["memory_mb"] == "ok"


@pytest.mark.asyncio
async def test_execute_dispatches_supported_operations(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    log_path = tmp_path / "agent.log"
    log_path.write_text(f"{now} ERROR core.new failure happened\n", encoding="utf-8")
    metrics_path = tmp_path / "runtime_metrics.json"
    metrics_path.write_text(json.dumps({"tasks_completed_total": 5}), encoding="utf-8")

    agent = MonitoringAgent(
        metrics_path=str(metrics_path),
        log_path=str(log_path),
        session_monitor=_FakeSessionMonitor(memory_mb=120.0),
    )
    agent._active_threads = lambda: 9
    agent._get_open_fds = lambda: 60

    health_resp = await agent.execute("health", _context(operation="health_check"))
    export_resp = await agent.execute("metrics", _context(operation="export_metrics", format="prometheus"))
    logs_resp = await agent.execute(
        "logs",
        _context(operation="check_logs", pattern="error", since_seconds=300),
    )
    threshold_resp = await agent.execute(
        "threshold",
        _context(operation="set_alert_threshold", metric="threads", threshold=400),
    )

    assert health_resp.structured_data["operation"] == "health_check"
    assert "maya_runtime_tasks_completed_total 5.0" in export_resp.structured_data["metrics"]
    assert len(logs_resp.structured_data["entries"]) == 1
    assert threshold_resp.structured_data["thresholds"]["threads"] == 400.0


@pytest.mark.asyncio
async def test_monitoring_agent_is_registered_and_signal_and_delegate_map():
    registry = AgentRegistry()
    assert registry.get_agent("monitoring") is not None

    manager = HandoffManager(registry)
    signal = HandoffSignal(
        signal_name="transfer_to_monitoring",
        reason="monitoring requested",
        execution_mode="planning",
        context_hint="health check",
    )
    assert manager.consume_signal(signal) == "monitoring"

    result = await manager.delegate(_request())

    assert result.status == "completed"
    assert result.source_agent == "monitoring"
    assert result.structured_payload["operation"] == "health_check"
