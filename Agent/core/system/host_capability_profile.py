"""Host capability profile collection for resource-aware delegation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import platform
import shutil
import subprocess
from typing import Literal

try:
    import psutil
except Exception:  # pragma: no cover - optional until dependency is installed
    psutil = None


@dataclass
class HostCapabilityProfile:
    os: str
    platform_release: str
    machine: str
    cpu_count: int
    ram_total_gb: float
    ram_available_gb: float
    disk_free_gb: float
    gpu_present: bool
    gpu_vendor: str | None
    gpu_name: str | None
    gpu_vram_gb: float | None
    runtime_mode: Literal["console", "voice", "worker"]
    safety_budget: Literal["restricted", "standard", "trusted"]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_prompt_block(self) -> str:
        gpu_summary = "absent"
        if self.gpu_present:
            gpu_summary = self.gpu_name or self.gpu_vendor or "present"
            if self.gpu_vram_gb is not None:
                gpu_summary = f"{gpu_summary} ({self.gpu_vram_gb}GB VRAM)"
        return (
            "## Host capability context\n"
            f"OS: {self.os} {self.platform_release}\n"
            f"CPU cores: {self.cpu_count}\n"
            f"RAM available: {self.ram_available_gb}GB of {self.ram_total_gb}GB\n"
            f"GPU: {gpu_summary}\n"
            f"Disk free: {self.disk_free_gb}GB\n"
            f"Runtime mode: {self.runtime_mode}\n"
            f"Safety budget: {self.safety_budget}\n\n"
            "Do not recommend operations that exceed available resources."
        )


def _round_gb(value_bytes: float) -> float:
    return round(float(value_bytes) / (1024.0 ** 3), 2)


def _probe_gpu() -> tuple[bool, str | None, str | None, float | None]:
    probes = [
        (
            "nvidia",
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
        ),
        (
            "amd",
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram"],
        ),
    ]
    for vendor, command in probes:
        if shutil.which(command[0]) is None:
            continue
        try:
            output = subprocess.check_output(command, text=True, timeout=2.0).strip()
        except Exception:
            continue
        if not output:
            continue
        if vendor == "nvidia":
            first_line = output.splitlines()[0]
            parts = [part.strip() for part in first_line.split(",")]
            gpu_name = parts[0] if parts else None
            vram_gb = None
            if len(parts) > 1:
                try:
                    vram_gb = round(float(parts[1]) / 1024.0, 2)
                except Exception:
                    vram_gb = None
            return True, vendor, gpu_name, vram_gb
        gpu_name = output.splitlines()[0].strip() or None
        return True, vendor, gpu_name, None
    return False, None, None, None


def collect_host_capability_profile(
    *,
    runtime_mode: str,
    safety_budget: str = "standard",
) -> HostCapabilityProfile:
    cpu_count = os.cpu_count() or 1
    if psutil is not None:
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(os.getcwd())
        ram_total_gb = _round_gb(vm.total)
        ram_available_gb = _round_gb(vm.available)
        disk_free_gb = _round_gb(disk.free)
    else:
        ram_total_gb = 0.0
        ram_available_gb = 0.0
        disk_free_gb = _round_gb(shutil.disk_usage(os.getcwd()).free)

    gpu_present, gpu_vendor, gpu_name, gpu_vram_gb = _probe_gpu()
    return HostCapabilityProfile(
        os=platform.system(),
        platform_release=platform.release(),
        machine=platform.machine(),
        cpu_count=cpu_count,
        ram_total_gb=ram_total_gb,
        ram_available_gb=ram_available_gb,
        disk_free_gb=disk_free_gb,
        gpu_present=gpu_present,
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
        runtime_mode="voice" if runtime_mode == "worker" else str(runtime_mode or "console"),
        safety_budget=str(safety_budget or "standard").strip().lower(),
    )


def refresh_host_capability_profile(profile: HostCapabilityProfile) -> HostCapabilityProfile:
    updated = collect_host_capability_profile(
        runtime_mode=profile.runtime_mode,
        safety_budget=profile.safety_budget,
    )
    updated.os = profile.os
    updated.platform_release = profile.platform_release
    updated.machine = profile.machine
    updated.cpu_count = profile.cpu_count
    updated.ram_total_gb = profile.ram_total_gb
    updated.gpu_present = profile.gpu_present
    updated.gpu_vendor = profile.gpu_vendor
    updated.gpu_name = profile.gpu_name
    updated.gpu_vram_gb = profile.gpu_vram_gb
    return updated
