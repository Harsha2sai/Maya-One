import json
import logging

from core.observability.maya_monitor import MayaMonitor


def test_maya_monitor_dual_write_to_audit_log(caplog):
    monitor = MayaMonitor(enable_otel=False, tracing_endpoint="")
    with caplog.at_level(logging.INFO, logger="audit"):
        monitor.log_route("research", 12.5, trace_id="t-1")
        monitor.log_handoff("planner", True, trace_id="t-1")
        monitor.log_tool("web_search", 4.2, trace_id="t-1")

    events = [json.loads(rec.message)["event"] for rec in caplog.records if rec.name == "audit"]
    assert "route_metric" in events
    assert "handoff_metric" in events
    assert "tool_metric" in events


def test_maya_monitor_flags_without_endpoint():
    monitor = MayaMonitor(enable_otel=False, tracing_endpoint="")
    assert monitor.tracing_enabled is False
