import json

import pytest

from core.agents.base import AgentContext
from core.agents.contracts import AgentHandoffRequest, HandoffSignal
from core.agents.handoff_manager import HandoffManager
from core.agents.registry import AgentRegistry
from core.agents.security_agent import SecurityAgent


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
        "handoff_id": "handoff-security-1",
        "trace_id": "trace-security-1",
        "conversation_id": "conversation-security-1",
        "task_id": "task-security-1",
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "security",
        "intent": "security_scan",
        "user_text": "run a security scan on this file",
        "context_slice": "User asked for a security review.",
        "execution_mode": "planning",
        "delegation_depth": 0,
        "max_depth": 1,
        "handoff_reason": "security_test",
        "metadata": {"user_id": "u1"},
    }
    payload.update(overrides)
    return AgentHandoffRequest(**payload)


@pytest.mark.asyncio
async def test_security_agent_scan_code_aggregates_bandit_and_semgrep(tmp_path):
    scan_file = tmp_path / "app.py"
    scan_file.write_text("print('debug')\n", encoding="utf-8")

    def _runner(command, _cwd):
        if command[0] == "bandit":
            return 1, json.dumps(
                {
                    "results": [
                        {
                            "test_id": "B101",
                            "issue_severity": "HIGH",
                            "issue_text": "assert used",
                            "filename": str(scan_file),
                            "line_number": 3,
                        }
                    ]
                }
            ), ""
        if command[0] == "semgrep":
            return 1, json.dumps(
                {
                    "results": [
                        {
                            "check_id": "python.lang.security.audit.eval",
                            "path": str(scan_file),
                            "start": {"line": 7},
                            "extra": {
                                "severity": "WARNING",
                                "message": "avoid eval",
                            },
                        }
                    ]
                }
            ), ""
        raise AssertionError(f"unexpected command: {command}")

    agent = SecurityAgent(
        command_runner=_runner,
        available_tools={"bandit", "semgrep"},
    )

    report = await agent.scan_code(str(scan_file))

    assert report.success is False
    assert len(report.findings) == 2
    assert {finding.tool for finding in report.findings} == {"bandit", "semgrep"}
    assert report.unavailable_tools == []


@pytest.mark.asyncio
async def test_security_agent_dependency_and_secret_scans_handle_tools():
    def _runner(command, _cwd):
        if command[0] == "safety":
            return 1, json.dumps(
                {
                    "vulnerabilities": [
                        {
                            "package_name": "requests",
                            "advisory": "example advisory",
                            "severity": "high",
                            "affected_versions": "<2.32",
                            "analyzed_version": "2.31.0",
                        }
                    ]
                }
            ), ""
        if command[0] == "detect-secrets":
            return 1, json.dumps(
                {
                    "results": {
                        "tmp.diff": [
                            {"type": "AWS Access Key", "line_number": 4},
                        ]
                    }
                }
            ), ""
        raise AssertionError(f"unexpected command: {command}")

    agent = SecurityAgent(
        command_runner=_runner,
        available_tools={"safety", "detect-secrets"},
    )

    vuln_report = await agent.check_dependencies()
    secret_report = await agent.scan_secrets("+ AWS_SECRET_ACCESS_KEY=abc123")

    assert vuln_report.success is False
    assert vuln_report.vulnerabilities[0].package == "requests"
    assert secret_report.success is False
    assert secret_report.secrets[0].type == "AWS Access Key"


@pytest.mark.asyncio
async def test_security_agent_reports_unavailable_tools_and_executes_from_context():
    agent = SecurityAgent(available_tools=set())

    code_report = await agent.scan_code("src/app.py")
    secret_report = await agent.scan_secrets("diff content")
    response = await agent.execute("security scan", _context(file_path="src/app.py"))

    assert code_report.success is False
    assert set(code_report.unavailable_tools) == {"bandit", "semgrep"}
    assert secret_report.unavailable_tools == ["detect-secrets"]
    assert response.structured_data["report"]["summary"] == "security scanners unavailable"


@pytest.mark.asyncio
async def test_security_agent_is_registered_and_security_signal_maps():
    registry = AgentRegistry()
    assert registry.get_agent("security") is not None

    manager = HandoffManager(registry)
    signal = HandoffSignal(
        signal_name="transfer_to_security",
        reason="security scan required",
        execution_mode="planning",
        context_hint="scan this diff",
    )

    assert manager.consume_signal(signal) == "security"

    result = await manager.delegate(
        _request(
            metadata={
                "user_id": "u1",
                "file_path": "src/app.py",
            }
        )
    )
    assert result.status == "completed"
    assert result.source_agent == "security"
    assert result.structured_payload["file_path"] == "src/app.py"
