"""P28 observability bridge: dual-write to audit log and OTel."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MayaMonitor:
    """
    Thin observability adapter.

    - Audit sink: emits structured JSON to the `audit` logger.
    - OTel sink: emits counters/histograms when available.
    - AgentScope tracing: activates tracing endpoint when configured.
    """

    def __init__(
        self,
        *,
        service_name: str = "maya",
        tracing_endpoint: Optional[str] = None,
        enable_otel: bool = True,
    ) -> None:
        self.service_name = str(service_name or "maya").strip() or "maya"
        self._audit_logger = logging.getLogger("audit")
        self._tracing_endpoint = str(
            tracing_endpoint or os.getenv("AGENTSCOPE_TRACING_ENDPOINT", "")
        ).strip()
        self._otel_enabled = bool(enable_otel)
        self._tracing_enabled = False
        self._meter: Any = None
        self._counters: Dict[str, Any] = {}
        self._histograms: Dict[str, Any] = {}

        self._setup_agentscope_tracing()
        self._setup_otel()

    def _setup_agentscope_tracing(self) -> None:
        if not self._tracing_endpoint:
            return
        try:
            from agentscope.tracing import setup_tracing

            setup_tracing(self._tracing_endpoint)
            self._tracing_enabled = True
            logger.info(
                "maya_monitor_agentscope_tracing_enabled endpoint=%s",
                self._tracing_endpoint,
            )
        except Exception as exc:
            logger.warning("maya_monitor_tracing_unavailable error=%s", exc)

    def _setup_otel(self) -> None:
        if not self._otel_enabled:
            return
        try:
            from opentelemetry import metrics

            self._meter = metrics.get_meter(self.service_name)
            self._counters["route"] = self._meter.create_counter(
                "maya.route.events",
                description="Route decision events",
            )
            self._counters["handoff"] = self._meter.create_counter(
                "maya.handoff.events",
                description="Handoff events",
            )
            self._counters["tool"] = self._meter.create_counter(
                "maya.tool.events",
                description="Tool events",
            )
            self._histograms["route_latency_ms"] = self._meter.create_histogram(
                "maya.route.latency_ms",
                description="Route latency in milliseconds",
                unit="ms",
            )
            self._histograms["tool_latency_ms"] = self._meter.create_histogram(
                "maya.tool.latency_ms",
                description="Tool latency in milliseconds",
                unit="ms",
            )
        except Exception as exc:
            self._meter = None
            logger.warning("maya_monitor_otel_unavailable error=%s", exc)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _audit(self, event: str, payload: Dict[str, Any]) -> None:
        entry = {
            "event": event,
            "timestamp": self._now(),
            "service": self.service_name,
            **payload,
        }
        self._audit_logger.info(json.dumps(entry, ensure_ascii=True))

    def log_route(self, route: str, latency_ms: float, trace_id: Optional[str] = None) -> None:
        route_name = str(route or "unknown").strip() or "unknown"
        latency = float(latency_ms or 0.0)
        payload = {"route": route_name, "latency_ms": latency, "trace_id": trace_id}
        self._audit("route_metric", payload)
        if self._meter is not None:
            attrs = {"route": route_name}
            if trace_id:
                attrs["trace_id"] = str(trace_id)
            self._counters["route"].add(1, attributes=attrs)
            self._histograms["route_latency_ms"].record(latency, attributes=attrs)

    def log_handoff(self, target: str, success: bool, trace_id: Optional[str] = None) -> None:
        target_name = str(target or "unknown").strip() or "unknown"
        status = "success" if bool(success) else "fail"
        payload = {"target": target_name, "success": bool(success), "trace_id": trace_id}
        self._audit("handoff_metric", payload)
        if self._meter is not None:
            attrs = {"target": target_name, "status": status}
            if trace_id:
                attrs["trace_id"] = str(trace_id)
            self._counters["handoff"].add(1, attributes=attrs)

    def log_tool(self, tool_name: str, latency_ms: float, trace_id: Optional[str] = None) -> None:
        normalized = str(tool_name or "unknown").strip() or "unknown"
        latency = float(latency_ms or 0.0)
        payload = {"tool": normalized, "latency_ms": latency, "trace_id": trace_id}
        self._audit("tool_metric", payload)
        if self._meter is not None:
            attrs = {"tool": normalized}
            if trace_id:
                attrs["trace_id"] = str(trace_id)
            self._counters["tool"].add(1, attributes=attrs)
            self._histograms["tool_latency_ms"].record(latency, attributes=attrs)

    @property
    def tracing_enabled(self) -> bool:
        return self._tracing_enabled

    @property
    def otel_enabled(self) -> bool:
        return self._meter is not None
