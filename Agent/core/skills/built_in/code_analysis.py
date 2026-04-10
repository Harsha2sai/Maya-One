"""Built-in skill that runs SecurityAgent static scan on a file path."""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.agents.security_agent import SecurityAgent

from ..base import BaseSkill, SkillPermissionLevel, SkillResult


class CodeAnalysisSkill(BaseSkill):
    def __init__(self, *, security_agent: Optional[SecurityAgent] = None) -> None:
        super().__init__(
            name="code_analysis",
            description="Run security-oriented static analysis on source files",
            permission_level=SkillPermissionLevel.STORAGE,
            permission_tool_name="read_file",
        )
        self._security_agent = security_agent or SecurityAgent()

    def validate(self, params: Dict[str, Any]) -> bool:
        if not super().validate(params):
            return False
        return bool(str((params or {}).get("file_path") or "").strip())

    async def execute(self, params: Dict[str, Any]) -> SkillResult:
        file_path = str((params or {}).get("file_path") or "").strip()
        report = await self._security_agent.scan_code(file_path)

        payload = report.to_dict() if hasattr(report, "to_dict") else {"report": report}
        return SkillResult(
            success=bool(payload.get("success", False)),
            data={"report": payload, "file_path": file_path},
            error=None if payload.get("success") else payload.get("summary"),
        )
