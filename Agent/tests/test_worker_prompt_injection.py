from types import SimpleNamespace

from core.context.role_context_builders.worker_context_builder import WorkerContextBuilder
from core.system.host_capability_profile import HostCapabilityProfile


def _system_message_content(worker_type: str | None, *, profile: HostCapabilityProfile | None = None) -> str:
    task = SimpleNamespace(description="Complete the assigned task")
    step = SimpleNamespace(description="Execute the step", worker=worker_type)
    chat_ctx = WorkerContextBuilder.build(task, step, worker_type=worker_type, host_capability_profile=profile)
    messages = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
    system_message = messages[0]
    content = system_message.content[0] if isinstance(system_message.content, list) else system_message.content
    return str(content)


def _profile() -> HostCapabilityProfile:
    return HostCapabilityProfile(
        os="Linux",
        platform_release="6.0",
        machine="x86_64",
        cpu_count=8,
        ram_total_gb=16.0,
        ram_available_gb=8.5,
        disk_free_gb=120.0,
        gpu_present=True,
        gpu_vendor="nvidia",
        gpu_name="RTX Test",
        gpu_vram_gb=8.0,
        runtime_mode="worker",
        safety_budget="standard",
    )


def test_general_worker_gets_base_plus_general_overlay():
    content = _system_message_content("general")
    assert "## Worker baseline" in content
    assert "## General worker overlay" in content


def test_research_worker_gets_base_plus_research_overlay():
    content = _system_message_content("research")
    assert "## Worker baseline" in content
    assert "## Research worker overlay" in content


def test_system_worker_gets_base_plus_system_overlay():
    content = _system_message_content("system", profile=_profile())
    assert "## Worker baseline" in content
    assert "## System worker overlay" in content


def test_automation_worker_gets_base_plus_automation_overlay():
    content = _system_message_content("automation", profile=_profile())
    assert "## Worker baseline" in content
    assert "## Automation worker overlay" in content


def test_system_worker_gets_host_capability_block():
    content = _system_message_content("system", profile=_profile())
    assert "## Host capability context" in content
    assert "CPU cores: 8" in content


def test_automation_worker_gets_host_capability_block():
    content = _system_message_content("automation", profile=_profile())
    assert "## Host capability context" in content
    assert "Disk free: 120.0GB" in content


def test_general_worker_does_not_get_host_capability_block():
    content = _system_message_content("general")
    assert "## Host capability context" not in content


def test_unspecified_worker_type_defaults_to_general():
    content = _system_message_content(None)
    assert "## General worker overlay" in content
