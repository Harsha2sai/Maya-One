"""Post-execution verification helpers for action truthfulness."""
from __future__ import annotations

import asyncio
import platform
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict

from core.action.constants import VerificationPolicy
from core.action.models import VerificationResult, VerificationTier

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


@dataclass
class _ProbeResult:
    tier: VerificationTier
    verified: bool
    confidence: float
    method: str
    message: str
    evidence: Dict[str, Any]


class ActionVerifier:
    def __init__(self, policy: VerificationPolicy | None = None) -> None:
        self.policy = policy or VerificationPolicy()

    async def verify(
        self,
        *,
        intent_id: str,
        tool_name: str,
        args: Dict[str, Any],
        normalized_result: Dict[str, Any],
        raw_result: Any = None,
    ) -> VerificationResult:
        probe = await self._run_probe(
            tool_name=tool_name,
            args=args,
            normalized_result=normalized_result,
            raw_result=raw_result,
        )
        return VerificationResult(
            intent_id=intent_id,
            tier=probe.tier,
            verified=probe.verified,
            confidence=probe.confidence,
            method=probe.method,
            message=probe.message,
            evidence=probe.evidence,
        )

    async def _run_probe(
        self,
        *,
        tool_name: str,
        args: Dict[str, Any],
        normalized_result: Dict[str, Any],
        raw_result: Any,
    ) -> _ProbeResult:
        payload = dict(normalized_result or {})
        tool = str(tool_name or "").strip().lower()
        if payload.get("success") is False:
            return _ProbeResult(
                tier=VerificationTier.failed,
                verified=False,
                confidence=0.95,
                method="normalized_result",
                message=str(payload.get("message") or "Tool reported failure."),
                evidence={"error_code": payload.get("error_code", "")},
            )

        if tool == "open_app":
            return await self._verify_open_app(args, payload)
        if tool == "close_app":
            return await self._verify_close_app(args, payload)
        if tool == "run_shell_command":
            return self._verify_shell(payload, raw_result)
        if tool == "web_search":
            return self._verify_search(payload)

        return _ProbeResult(
            tier=VerificationTier.weak,
            verified=bool(payload.get("success", True)),
            confidence=0.55,
            method="generic_tool_success",
            message="Tool reported success but strong verification is unavailable.",
            evidence={"tool_name": tool},
        )

    @staticmethod
    def _verify_shell(payload: Dict[str, Any], raw_result: Any) -> _ProbeResult:
        result_text = str(payload.get("result") or payload.get("message") or raw_result or "").strip()
        if payload.get("error_code"):
            return _ProbeResult(
                tier=VerificationTier.failed,
                verified=False,
                confidence=0.9,
                method="shell_error_code",
                message="Shell command returned an error code.",
                evidence={"error_code": payload.get("error_code")},
            )
        if result_text:
            return _ProbeResult(
                tier=VerificationTier.medium,
                verified=True,
                confidence=0.7,
                method="shell_output_observed",
                message="Shell command produced output.",
                evidence={"output_preview": result_text[:120]},
            )
        return _ProbeResult(
            tier=VerificationTier.inconclusive,
            verified=False,
            confidence=0.4,
            method="shell_no_output",
            message="No output to confirm shell command result.",
            evidence={},
        )

    @staticmethod
    def _verify_search(payload: Dict[str, Any]) -> _ProbeResult:
        has_results = bool(payload.get("results")) or bool(str(payload.get("summary") or "").strip())
        if has_results:
            return _ProbeResult(
                tier=VerificationTier.medium,
                verified=True,
                confidence=0.75,
                method="search_results_present",
                message="Search returned results.",
                evidence={"results_count": len(payload.get("results") or [])},
            )
        return _ProbeResult(
            tier=VerificationTier.inconclusive,
            verified=False,
            confidence=0.45,
            method="search_no_results",
            message="Search completed but had no verifiable results.",
            evidence={},
        )

    async def _verify_open_app(self, args: Dict[str, Any], payload: Dict[str, Any]) -> _ProbeResult:
        app_name = str(args.get("app_name") or payload.get("app_name") or "").strip()
        opened_in_browser = "browser" in str(payload.get("message") or "").lower()
        if opened_in_browser:
            return _ProbeResult(
                tier=VerificationTier.medium,
                verified=True,
                confidence=0.7,
                method="web_fallback_open",
                message="Request opened through browser fallback.",
                evidence={"app_name": app_name},
            )
        process_name = self._process_candidate(app_name)
        if not process_name:
            return _ProbeResult(
                tier=VerificationTier.inconclusive,
                verified=False,
                confidence=0.4,
                method="missing_process_name",
                message="Unable to derive process target for verification.",
                evidence={"app_name": app_name},
            )
        running, probe_method, probe_evidence = await self._is_process_running(process_name)
        if probe_method.endswith("_unavailable"):
            return _ProbeResult(
                tier=VerificationTier.inconclusive,
                verified=False,
                confidence=0.4,
                method=probe_method,
                message="Process verification is unavailable on this host.",
                evidence={"process": process_name, **probe_evidence},
            )
        if running:
            return _ProbeResult(
                tier=VerificationTier.strong,
                verified=True,
                confidence=0.95,
                method=probe_method,
                message="Verified process is running.",
                evidence={"process": process_name, **probe_evidence},
            )
        return _ProbeResult(
            tier=VerificationTier.inconclusive,
            verified=False,
            confidence=0.45,
            method=probe_method,
            message="Could not verify the app process is running.",
            evidence={"process": process_name, **probe_evidence},
        )

    async def _verify_close_app(self, args: Dict[str, Any], payload: Dict[str, Any]) -> _ProbeResult:
        app_name = str(args.get("app_name") or payload.get("app_name") or "").strip()
        process_name = self._process_candidate(app_name)
        if not process_name:
            return _ProbeResult(
                tier=VerificationTier.inconclusive,
                verified=False,
                confidence=0.4,
                method="missing_process_name",
                message="Unable to derive process target for close verification.",
                evidence={"app_name": app_name},
            )
        running, probe_method, probe_evidence = await self._is_process_running(process_name)
        if probe_method.endswith("_unavailable"):
            return _ProbeResult(
                tier=VerificationTier.inconclusive,
                verified=False,
                confidence=0.4,
                method=probe_method,
                message="Process verification is unavailable on this host.",
                evidence={"process": process_name, **probe_evidence},
            )
        if not running:
            return _ProbeResult(
                tier=VerificationTier.strong,
                verified=True,
                confidence=0.93,
                method=probe_method,
                message="Verified process is no longer running.",
                evidence={"process": process_name, **probe_evidence},
            )
        return _ProbeResult(
            tier=VerificationTier.inconclusive,
            verified=False,
            confidence=0.45,
            method=probe_method,
            message="Process still appears to be running.",
            evidence={"process": process_name, **probe_evidence},
        )

    @staticmethod
    def _process_candidate(app_name: str) -> str:
        raw = str(app_name or "").strip().lower()
        if not raw:
            return ""
        if raw.startswith("youtube search for"):
            return "browser"
        tokens = [token for token in re.split(r"[^a-z0-9._-]+", raw) if token]
        return tokens[0] if tokens else ""

    @staticmethod
    async def _pgrep(process_name: str) -> bool:
        if not process_name:
            return False

        def _run() -> bool:
            try:
                result = subprocess.run(
                    ["pgrep", "-f", process_name],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=1.5,
                )
                return result.returncode == 0 and bool(str(result.stdout or "").strip())
            except Exception:
                return False

        return await asyncio.to_thread(_run)

    @staticmethod
    def _psutil_process_running(process_name: str) -> bool:
        if psutil is None:
            return False
        needle = str(process_name or "").strip().lower()
        if not needle:
            return False
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                name = str(proc.info.get("name") or "").lower()
                cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            except Exception:
                continue
            if needle in name or needle in cmdline:
                return True
        return False

    @staticmethod
    def _tasklist_process_running(process_name: str) -> tuple[bool, bool]:
        if shutil.which("tasklist") is None:
            return False, False
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=1.5,
            )
        except Exception:
            return False, False

        needle = str(process_name or "").strip().lower()
        if not needle:
            return False, True
        output = str(result.stdout or "").lower()
        return needle in output, True

    async def _is_process_running(self, process_name: str) -> tuple[bool, str, Dict[str, Any]]:
        system_name = platform.system().lower()

        if psutil is not None:
            running = await asyncio.to_thread(self._psutil_process_running, process_name)
            return running, "psutil_probe", {"platform": system_name}

        if system_name.startswith("win"):
            running, available = await asyncio.to_thread(self._tasklist_process_running, process_name)
            if not available:
                return False, "tasklist_unavailable", {"platform": system_name}
            return running, "tasklist_probe", {"platform": system_name}

        if shutil.which("pgrep") is None:
            return False, "pgrep_unavailable", {"platform": system_name}
        running = await self._pgrep(process_name)
        return running, "pgrep_probe", {"platform": system_name}


def categorize_shell_error(command: str, stderr_text: str) -> str:
    cmd = str(command or "").strip()
    stderr_l = str(stderr_text or "").lower()
    if "not found" in stderr_l:
        try:
            token = shlex.split(cmd)[0]
        except Exception:
            token = cmd.split(" ", 1)[0]
        return f"command_not_found:{token}"
    if "permission denied" in stderr_l:
        return "permission_denied"
    if "timed out" in stderr_l:
        return "timeout"
    return "shell_error"
