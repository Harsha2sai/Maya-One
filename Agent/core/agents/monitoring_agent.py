"""Monitoring agent for health checks, log scans, and metrics export."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agents.base import AgentContext, AgentResponse, SpecializedAgent
from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    status: str
    healthy: bool
    memory_mb: float
    threads: int
    open_fds: int
    checks: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "healthy": self.healthy,
            "memory_mb": self.memory_mb,
            "threads": self.threads,
            "open_fds": self.open_fds,
            "checks": dict(self.checks or {}),
            "timestamp": self.timestamp,
        }


@dataclass
class LogEntry:
    timestamp: str
    level: str
    source: str
    message: str
    raw: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "source": self.source,
            "message": self.message,
            "raw": self.raw,
        }


class MonitoringAgent(SpecializedAgent):
    """Health monitoring and metrics collection for system observability."""

    DEFAULT_THRESHOLDS = {
        "memory_mb": 2000.0,
        "threads": 250.0,
        "open_fds": 4096.0,
    }
    SUPPORTED_EXPORT_FORMATS = {"prometheus"}

    def __init__(
        self,
        *,
        metrics_path: Optional[str] = None,
        log_path: Optional[str] = None,
        session_monitor: Any | None = None,
    ) -> None:
        super().__init__("monitoring")
        self._metrics_path = Path(
            metrics_path or "verification/runtime_validation/runtime_metrics.json"
        )
        self._log_path = str(log_path or os.getenv("MAYA_LOG_PATH", ""))
        self._session_monitor = session_monitor
        self._alert_thresholds: Dict[str, float] = dict(self.DEFAULT_THRESHOLDS)
        self._monitoring_keywords = [
            "monitor",
            "monitoring",
            "health check",
            "metrics",
            "prometheus",
            "alerts",
            "threshold",
            "logs",
        ]

    async def health_check(self) -> HealthStatus:
        """Return system health snapshot."""
        memory_mb = float(self._get_memory_usage())
        threads = int(self._active_threads())
        open_fds = int(self._get_open_fds())

        threshold_checks = {
            "memory_mb": "ok" if memory_mb <= self._alert_thresholds["memory_mb"] else "breach",
            "threads": "ok" if threads <= self._alert_thresholds["threads"] else "breach",
            "open_fds": "ok" if open_fds <= self._alert_thresholds["open_fds"] else "breach",
        }
        healthy = all(status == "ok" for status in threshold_checks.values())
        checks = {
            "thresholds": dict(self._alert_thresholds),
            "threshold_checks": threshold_checks,
            "dependency_parity": self._dependency_parity_checks(),
        }

        return HealthStatus(
            status="ok" if healthy else "degraded",
            healthy=healthy,
            memory_mb=memory_mb,
            threads=threads,
            open_fds=open_fds,
            checks=checks,
        )

    async def check_logs(self, pattern: str, since: timedelta) -> List[LogEntry]:
        """Search logs for patterns."""
        path = Path(str(self._log_path or os.getenv("MAYA_LOG_PATH", "")).strip())
        if not path.exists() or not path.is_file():
            return []

        compiled = re.compile(str(pattern or ".*"), re.IGNORECASE)
        cutoff = datetime.now(timezone.utc) - (since if isinstance(since, timedelta) else timedelta(0))
        matches: List[LogEntry] = []

        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parsed = self._parse_log_line(raw)
            if not parsed:
                continue
            entry_time = self._parse_timestamp(parsed.timestamp)
            if entry_time and entry_time < cutoff:
                continue
            if compiled.search(parsed.raw) or compiled.search(parsed.message):
                matches.append(parsed)
        return matches

    async def export_metrics(self, format: str = "prometheus") -> str:
        """Export metrics in specified format."""
        normalized = str(format or "").strip().lower()
        if normalized not in self.SUPPORTED_EXPORT_FORMATS:
            raise ValueError(f"unsupported metrics format: {format}")
        payload = self._read_runtime_metrics()
        return self._to_prometheus(payload)

    async def set_alert_threshold(self, metric: str, threshold: float) -> None:
        """Configure alert threshold for a metric."""
        normalized = str(metric or "").strip()
        if normalized not in self._alert_thresholds:
            raise ValueError(f"unknown threshold metric: {metric}")
        value = float(threshold)
        if value <= 0:
            raise ValueError("threshold must be greater than zero")
        self._alert_thresholds[normalized] = value

    async def can_handle(self, request: str, context: AgentContext) -> float:
        lowered = str(request or "").lower()
        matches = sum(1 for keyword in self._monitoring_keywords if keyword in lowered)
        if matches == 0:
            return 0.0
        return min(1.0, 0.35 + (0.2 * min(matches, 3)))

    async def can_accept(self, request: AgentHandoffRequest) -> AgentCapabilityMatch:
        confidence = await self.can_handle(request.user_text, self._legacy_context_from_request(request))
        return AgentCapabilityMatch(
            agent_name=self.name,
            confidence=confidence,
            reason="monitoring_keyword_match",
            hard_constraints_passed=bool(str(request.user_text or "").strip()),
        )

    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        metadata = dict(context.custom_data or {})
        operation = str(metadata.get("operation") or "health_check").strip().lower()

        if operation == "health_check":
            report = await self.health_check()
            return AgentResponse(
                display_text=f"System health: {report.status}.",
                voice_text=f"System health is {report.status}.",
                mode="direct",
                confidence=0.9,
                structured_data={"operation": operation, "report": report.to_dict()},
            )
        if operation == "check_logs":
            entries = await self.check_logs(
                str(metadata.get("pattern") or ""),
                timedelta(seconds=float(metadata.get("since_seconds", 300))),
            )
            return AgentResponse(
                display_text=f"Found {len(entries)} matching log entries.",
                voice_text=f"Found {len(entries)} matching log entries.",
                mode="direct",
                confidence=0.9,
                structured_data={
                    "operation": operation,
                    "entries": [entry.to_dict() for entry in entries],
                },
            )
        if operation == "export_metrics":
            metrics_output = await self.export_metrics(str(metadata.get("format") or "prometheus"))
            return AgentResponse(
                display_text="Metrics export generated.",
                voice_text="Metrics export generated.",
                mode="direct",
                confidence=0.9,
                structured_data={"operation": operation, "metrics": metrics_output},
            )
        if operation == "set_alert_threshold":
            await self.set_alert_threshold(
                str(metadata.get("metric") or ""),
                float(metadata.get("threshold")),
            )
            return AgentResponse(
                display_text="Alert threshold updated.",
                voice_text="Alert threshold updated.",
                mode="direct",
                confidence=0.9,
                structured_data={
                    "operation": operation,
                    "thresholds": dict(self._alert_thresholds),
                },
            )

        raise ValueError(f"unsupported operation: {operation}")

    async def handle(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        metadata = dict(request.metadata or {})
        operation = str(metadata.get("operation") or "health_check").strip().lower()
        structured_payload = {
            "operation": operation,
            "log_path": self._log_path or os.getenv("MAYA_LOG_PATH", ""),
            "metrics_path": str(self._metrics_path),
            "thresholds": dict(self._alert_thresholds),
            "supported_formats": sorted(self.SUPPORTED_EXPORT_FORMATS),
        }
        return AgentHandoffResult(
            handoff_id=request.handoff_id,
            trace_id=request.trace_id,
            source_agent=self.name,
            status="completed",
            user_visible_text="Monitoring intent validated.",
            voice_text=None,
            structured_payload=structured_payload,
            next_action="continue",
        )

    def get_capabilities(self) -> list:
        return [
            "System health snapshots (memory, threads, file descriptors)",
            "Log pattern search with recency filter",
            "Prometheus metrics export",
            "Runtime alert threshold tuning (in-memory)",
        ]

    def _get_session_monitor(self):
        if self._session_monitor is not None:
            return self._session_monitor
        from telemetry.session_monitor import get_session_monitor

        self._session_monitor = get_session_monitor()
        return self._session_monitor

    def _get_memory_usage(self) -> float:
        monitor = self._get_session_monitor()
        memory_reader = getattr(monitor, "get_memory_usage", None)
        if callable(memory_reader):
            return float(memory_reader())
        return 0.0

    @staticmethod
    def _active_threads() -> int:
        return int(threading.active_count())

    @staticmethod
    def _get_open_fds() -> int:
        try:
            return len(os.listdir("/proc/self/fd"))
        except Exception:
            return 0

    def _dependency_parity_checks(self) -> Dict[str, str]:
        llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()
        if llm_provider == "groq":
            key_present = bool(os.getenv("GROQ_API_KEY", "").strip())
        elif llm_provider == "openai":
            key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
        else:
            key_present = bool(
                os.getenv("GROQ_API_KEY", "").strip()
                or os.getenv("OPENAI_API_KEY", "").strip()
            )
        livekit_ok = bool(
            os.getenv("LIVEKIT_URL", "").strip()
            and os.getenv("LIVEKIT_API_KEY", "").strip()
            and os.getenv("LIVEKIT_API_SECRET", "").strip()
        )
        return {
            "llm_key": "ok" if key_present else "missing",
            "livekit_credentials": "ok" if livekit_ok else "missing",
        }

    def _read_runtime_metrics(self) -> Dict[str, Any]:
        if not self._metrics_path.exists() or not self._metrics_path.is_file():
            return {}
        text = self._metrics_path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _to_prometheus(payload: Dict[str, Any]) -> str:
        lines: List[str] = []
        for key, value in (payload or {}).items():
            metric_name = f"maya_runtime_{MonitoringAgent._sanitize_metric_name(key)}"
            if isinstance(value, (int, float)):
                lines.append(f"{metric_name} {float(value)}")
                continue
            if isinstance(value, list):
                numeric = [float(item) for item in value if isinstance(item, (int, float))]
                lines.append(f"{metric_name}_count {len(numeric)}")
                lines.append(f"{metric_name}_sum {sum(numeric)}")
                if numeric:
                    lines.append(f"{metric_name}_avg {sum(numeric) / len(numeric)}")
        return "\n".join(lines)

    @staticmethod
    def _sanitize_metric_name(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", str(name or "").strip()).lower()

    @staticmethod
    def _parse_timestamp(text: str) -> Optional[datetime]:
        value = str(text or "").strip()
        if not value:
            return None
        try:
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _parse_log_line(self, raw: str) -> Optional[LogEntry]:
        line = str(raw or "").rstrip("\n")
        if not line:
            return None

        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                return LogEntry(
                    timestamp=str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat()),
                    level=str(payload.get("level") or "INFO"),
                    source=str(payload.get("source") or "unknown"),
                    message=str(payload.get("message") or payload.get("msg") or ""),
                    raw=line,
                )

        basic_match = re.match(
            r"^(?P<timestamp>\S+)\s+(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+(?P<source>\S+)\s*(?P<message>.*)$",
            line,
        )
        if basic_match:
            fields = basic_match.groupdict()
            return LogEntry(
                timestamp=str(fields.get("timestamp") or datetime.now(timezone.utc).isoformat()),
                level=str(fields.get("level") or "INFO"),
                source=str(fields.get("source") or "unknown"),
                message=str(fields.get("message") or ""),
                raw=line,
            )

        logger_style_match = re.match(
            r"^(?P<timestamp>\S+)\s*-\s*(?P<source>\S+)\s*-\s*(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*-\s*(?P<message>.*)$",
            line,
        )
        if logger_style_match:
            fields = logger_style_match.groupdict()
            return LogEntry(
                timestamp=str(fields.get("timestamp") or datetime.now(timezone.utc).isoformat()),
                level=str(fields.get("level") or "INFO"),
                source=str(fields.get("source") or "unknown"),
                message=str(fields.get("message") or ""),
                raw=line,
            )

        return LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level="INFO",
            source="unknown",
            message=line,
            raw=line,
        )
