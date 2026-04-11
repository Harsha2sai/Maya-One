"""Security scanning agent for code, dependencies, and secret detection."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.agents.base import AgentContext, AgentResponse, SpecializedAgent
from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult


@dataclass
class SecurityFinding:
    tool: str
    rule_id: str
    severity: str
    message: str
    path: Optional[str] = None
    line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "line": self.line,
        }


@dataclass
class SecurityReport:
    success: bool
    summary: str
    findings: List[SecurityFinding] = field(default_factory=list)
    unavailable_tools: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary,
            "findings": [finding.to_dict() for finding in self.findings],
            "unavailable_tools": list(self.unavailable_tools or []),
        }


@dataclass
class VulnerabilityFinding:
    package: str
    advisory: str
    severity: str
    affected_versions: Optional[str] = None
    installed_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package": self.package,
            "advisory": self.advisory,
            "severity": self.severity,
            "affected_versions": self.affected_versions,
            "installed_version": self.installed_version,
        }


@dataclass
class VulnerabilityReport:
    success: bool
    summary: str
    vulnerabilities: List[VulnerabilityFinding] = field(default_factory=list)
    unavailable_tools: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary,
            "vulnerabilities": [item.to_dict() for item in self.vulnerabilities],
            "unavailable_tools": list(self.unavailable_tools or []),
        }


@dataclass
class SecretFinding:
    type: str
    filename: str
    line: Optional[int] = None
    tool: str = "detect-secrets"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "filename": self.filename,
            "line": self.line,
            "tool": self.tool,
        }


@dataclass
class SecretReport:
    success: bool
    summary: str
    secrets: List[SecretFinding] = field(default_factory=list)
    unavailable_tools: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary,
            "secrets": [item.to_dict() for item in self.secrets],
            "unavailable_tools": list(self.unavailable_tools or []),
        }


class SecurityAgent(SpecializedAgent):
    """Security scanning and vulnerability detection."""

    def __init__(
        self,
        *,
        command_runner: Optional[Callable[[List[str], Optional[str]], Any]] = None,
        available_tools: Optional[set[str]] = None,
    ) -> None:
        super().__init__("security")
        self._command_runner = command_runner or self._default_command_runner
        self._available_tools = set(available_tools) if available_tools is not None else {
            tool for tool in ("bandit", "semgrep", "safety", "detect-secrets") if shutil.which(tool)
        }
        self._security_keywords = [
            "security",
            "vulnerability",
            "secret",
            "dependency audit",
            "scan code",
            "semgrep",
            "bandit",
            "safety",
            "detect-secrets",
        ]

    async def scan_code(self, file_path: str) -> SecurityReport:
        """Run bandit + semgrep."""
        path = str(file_path or "").strip()
        if not path:
            raise ValueError("file_path is required")

        findings: List[SecurityFinding] = []
        unavailable: List[str] = []

        if "bandit" in self._available_tools:
            findings.extend(await self._run_bandit(path))
        else:
            unavailable.append("bandit")

        if "semgrep" in self._available_tools:
            findings.extend(await self._run_semgrep(path))
        else:
            unavailable.append("semgrep")

        if findings:
            summary = f"security scan found {len(findings)} issues"
            success = False
        elif len(unavailable) == 2:
            summary = "security scanners unavailable"
            success = False
        else:
            summary = "security scan completed with no findings"
            success = True

        return SecurityReport(
            success=success,
            summary=summary,
            findings=findings,
            unavailable_tools=unavailable,
        )

    async def check_dependencies(self) -> VulnerabilityReport:
        """Run safety check."""
        if "safety" not in self._available_tools:
            return VulnerabilityReport(
                success=False,
                summary="dependency scanner unavailable",
                vulnerabilities=[],
                unavailable_tools=["safety"],
            )

        exit_code, stdout, stderr = await self._run_command(["safety", "check", "--json"])
        payload = self._load_json(stdout, stderr)
        if isinstance(payload, list):
            items = payload
        else:
            items = payload.get("vulnerabilities") or payload.get("issues") or []
        vulnerabilities: List[VulnerabilityFinding] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            vulnerabilities.append(
                VulnerabilityFinding(
                    package=str(item.get("package_name") or item.get("package") or "unknown"),
                    advisory=str(item.get("advisory") or item.get("vulnerability") or "dependency issue"),
                    severity=str(item.get("severity") or "high").lower(),
                    affected_versions=str(item.get("affected_versions") or item.get("specs") or "") or None,
                    installed_version=str(item.get("analyzed_version") or item.get("installed_version") or "") or None,
                )
            )
        summary = (
            f"dependency scan found {len(vulnerabilities)} vulnerabilities"
            if vulnerabilities
            else "dependency scan completed with no vulnerabilities"
        )
        return VulnerabilityReport(
            success=exit_code == 0 and not vulnerabilities,
            summary=summary,
            vulnerabilities=vulnerabilities,
        )

    async def scan_secrets(self, diff: str) -> SecretReport:
        """Run detect-secrets."""
        if "detect-secrets" not in self._available_tools:
            return SecretReport(
                success=False,
                summary="secret scanner unavailable",
                secrets=[],
                unavailable_tools=["detect-secrets"],
            )

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".diff", delete=True) as handle:
            handle.write(str(diff or ""))
            handle.flush()
            exit_code, stdout, stderr = await self._run_command(["detect-secrets", "scan", handle.name])

        payload = self._load_json(stdout, stderr)
        raw_results = payload.get("results") or {}
        secrets: List[SecretFinding] = []
        for filename, items in raw_results.items():
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                secrets.append(
                    SecretFinding(
                        type=str(item.get("type") or "secret"),
                        filename=str(filename),
                        line=item.get("line_number"),
                    )
                )
        summary = f"secret scan found {len(secrets)} secrets" if secrets else "secret scan completed with no secrets"
        return SecretReport(
            success=exit_code == 0 and not secrets,
            summary=summary,
            secrets=secrets,
        )

    async def can_handle(self, request: str, context: AgentContext) -> float:
        lowered = str(request or "").lower()
        matches = sum(1 for keyword in self._security_keywords if keyword in lowered)
        if matches == 0:
            return 0.0
        return min(1.0, 0.35 + (0.2 * min(matches, 3)))

    async def can_accept(self, request: AgentHandoffRequest) -> AgentCapabilityMatch:
        confidence = await self.can_handle(request.user_text, self._legacy_context_from_request(request))
        return AgentCapabilityMatch(
            agent_name=self.name,
            confidence=confidence,
            reason="security_keyword_match",
            hard_constraints_passed=bool(str(request.user_text or "").strip()),
        )

    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        metadata = dict(context.custom_data or {})
        if metadata.get("file_path"):
            report = await self.scan_code(str(metadata.get("file_path")))
            return AgentResponse(
                display_text=report.summary,
                voice_text=report.summary,
                mode="direct",
                confidence=0.9,
                structured_data={"report": report.to_dict()},
            )
        if metadata.get("dependency_check"):
            report = await self.check_dependencies()
            return AgentResponse(
                display_text=report.summary,
                voice_text=report.summary,
                mode="direct",
                confidence=0.9,
                structured_data={"report": report.to_dict()},
            )
        if metadata.get("diff"):
            report = await self.scan_secrets(str(metadata.get("diff")))
            return AgentResponse(
                display_text=report.summary,
                voice_text=report.summary,
                mode="direct",
                confidence=0.9,
                structured_data={"report": report.to_dict()},
            )
        return AgentResponse(
            display_text="Security scan intent accepted. Provide a file path, dependency request, or diff payload.",
            voice_text="Security scan intent accepted.",
            mode="direct",
            confidence=0.8,
            structured_data={"available_tools": sorted(self._available_tools)},
        )

    async def handle(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        metadata = dict(request.metadata or {})
        structured_payload = {
            "file_path": metadata.get("file_path"),
            "dependency_check": bool(metadata.get("dependency_check")),
            "has_diff": bool(metadata.get("diff")),
            "available_tools": sorted(self._available_tools),
        }
        return AgentHandoffResult(
            handoff_id=request.handoff_id,
            trace_id=request.trace_id,
            source_agent=self.name,
            status="completed",
            user_visible_text="Security intent validated.",
            voice_text=None,
            structured_payload=structured_payload,
            next_action="continue",
        )

    def get_capabilities(self) -> list:
        return [
            "Static code security scanning",
            "Dependency vulnerability scanning",
            "Secret detection in diffs",
        ]

    async def _run_bandit(self, file_path: str) -> List[SecurityFinding]:
        _exit_code, stdout, stderr = await self._run_command(["bandit", "-f", "json", "-q", file_path])
        payload = self._load_json(stdout, stderr)
        findings: List[SecurityFinding] = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            findings.append(
                SecurityFinding(
                    tool="bandit",
                    rule_id=str(item.get("test_id") or "bandit"),
                    severity=str(item.get("issue_severity") or "medium").lower(),
                    message=str(item.get("issue_text") or "security finding"),
                    path=str(item.get("filename") or file_path),
                    line=item.get("line_number"),
                )
            )
        return findings

    async def _run_semgrep(self, file_path: str) -> List[SecurityFinding]:
        _exit_code, stdout, stderr = await self._run_command(
            ["semgrep", "--json", "--config", "auto", file_path]
        )
        payload = self._load_json(stdout, stderr)
        findings: List[SecurityFinding] = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            extra = item.get("extra") or {}
            start = item.get("start") or {}
            findings.append(
                SecurityFinding(
                    tool="semgrep",
                    rule_id=str(item.get("check_id") or "semgrep"),
                    severity=str(extra.get("severity") or "medium").lower(),
                    message=str(extra.get("message") or "security finding"),
                    path=str(item.get("path") or file_path),
                    line=start.get("line"),
                )
            )
        return findings

    async def _run_command(self, command: List[str]):
        result = self._command_runner(command, None)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    @staticmethod
    def _load_json(stdout: str, stderr: str) -> Dict[str, Any]:
        text = str(stdout or "").strip() or str(stderr or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"results": parsed}
        return {}

    @staticmethod
    def _default_command_runner(command: List[str], cwd: Optional[str]):
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr
