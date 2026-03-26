#!/usr/bin/env python3
"""
Phase Gatekeeper validation runner for Phase 4 certification.

This script validates structural readiness, runs required test examples,
compares direct-backend vs flutter-triggered paths, and emits certification JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import difflib
import json
import os
import platform
import re
import sys
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request
from urllib.error import URLError, HTTPError

import edge_tts

try:
    import importlib.metadata as importlib_metadata
except Exception:  # pragma: no cover
    import importlib_metadata  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "Agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


REQUIRED_FILES = [
    AGENT_ROOT / "core/tasks/planning_engine.py",
    AGENT_ROOT / "core/tasks/planner_schema_validator.py",
    AGENT_ROOT / "core/tasks/task_worker.py",
    AGENT_ROOT / "core/tasks/atomic_task_state.py",
    AGENT_ROOT / "core/tools/tool_manager.py",
    AGENT_ROOT / "core/tasks/workers/tool_registry.py",
    AGENT_ROOT / "core/orchestrator/agent_orchestrator.py",
    AGENT_ROOT / "core/runtime/lifecycle.py",
    AGENT_ROOT / "core/runtime/console_harness.py",
    AGENT_ROOT / "agent.py",
]


EXAMPLES = [
    {
        "id": "ex1",
        "name": "Simple task creation",
        "prompt": "Create task: remind me to review sprint notes in 30 minutes.",
        "category": "Core functionality",
        "difficulty": "L1",
        "scenario": "task_followup",
    },
    {
        "id": "ex2",
        "name": "Follow-up task edit",
        "prompt": "Update that task to run in 45 minutes instead.",
        "category": "Multi-turn conversational integrity",
        "difficulty": "L2",
        "scenario": "task_followup",
    },
    {
        "id": "ex3",
        "name": "Tool-backed info",
        "prompt": "What is the current time?",
        "category": "Tool invocation correctness",
        "difficulty": "L1",
        "scenario": "tool_time",
    },
    {
        "id": "ex4",
        "name": "Ambiguous intent",
        "prompt": "Schedule it for tomorrow morning and ensure I do not miss it.",
        "category": "Edge case handling",
        "difficulty": "L3",
        "scenario": "ambiguous_schedule",
    },
    {
        "id": "ex5",
        "name": "Malformed input recovery",
        "prompt": "creat tasl[]{}?? plz",
        "category": "Failure recovery",
        "difficulty": "L5",
        "scenario": "malformed_recovery",
    },
    {
        "id": "ex6",
        "name": "Multi-step workflow",
        "prompt": "Create task: research top three AI conferences and draft a summary.",
        "category": "Latency stress",
        "difficulty": "L4",
        "scenario": "multi_step_task",
    },
]

FEATURE_CATEGORIES = [
    "Core functionality",
    "Edge case handling",
    "Failure recovery",
    "Latency stress",
    "Memory interaction",
    "Tool invocation correctness",
    "Multi-turn conversational integrity",
    "Cross-platform consistency",
]

PROBE_DIAG_REPORT_PATH = AGENT_ROOT / "reports" / "livekit_probe_diag.json"

TOOL_CAPABILITY_FAMILIES = [
    {
        "family": "time_date",
        "expect_tool_event": True,
        "prompts": ["what time is it", "tell me the current time", "date and time please"],
    },
    {
        "family": "app_opening",
        "expect_tool_event": True,
        "prompts": ["open my files", "open file manager", "open calculator"],
    },
    {
        "family": "media_opening_search",
        "expect_tool_event": True,
        "prompts": ["play some music", "play songs", "open youtube and search for lo-fi music"],
    },
    {
        "family": "weather",
        "expect_tool_event": True,
        "prompts": ["what's the weather", "weather update", "tell me weather in new york"],
    },
    {
        "family": "web_search",
        "expect_tool_event": True,
        "prompts": ["search the web for python asyncio tutorial", "look up latest AI news", "web search for linux flutter setup"],
    },
    {
        "family": "reminders",
        "expect_tool_event": True,
        "prompts": ["list my reminders", "set a reminder in 5 minutes to stretch", "delete my latest reminder"],
    },
    {
        "family": "task_status",
        "expect_tool_event": False,
        "prompts": ["what is the status of my latest task?", "how far is my task", "show my active task progress"],
    },
    {
        "family": "recovery_clarification",
        "expect_tool_event": False,
        "prompts": ["open my fless", "creat tasl[]{}?? plz", "schedule it tomorrow morning and don't let me miss it"],
    },
]


@dataclass
class StructuralCheck:
    name: str
    passed: bool
    details: str


@dataclass
class ExampleRun:
    example_id: str
    path: str
    prompt: str
    response: str
    latency_ms: float
    passed: bool
    error: Optional[str] = None
    error_type: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExampleParity:
    example_id: str
    direct_passed: bool
    flutter_passed: bool
    semantic_match: bool
    formatting_match: bool
    latency_delta_ms: float
    passed: bool


def build_scenario_participant(base: str, scenario: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in f"{base}-{scenario}")
    return safe[:64]


def post_json(url: str, payload: Dict[str, Any], timeout_s: float = 10.0) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    return json.loads(raw) if raw.strip() else {}


def check_health(health_url: str, timeout_s: float = 3.0) -> Tuple[bool, str]:
    try:
        with request.urlopen(health_url, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
        return True, body or "ok"
    except HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except URLError as e:
        return False, str(e.reason)
    except Exception as e:
        return False, str(e)


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    try:
        parts = str(token).split(".")
        if len(parts) != 3:
            return {"decode_error": f"unexpected_jwt_parts:{len(parts)}"}
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        decoded = json.loads(payload.decode("utf-8"))
        return decoded if isinstance(decoded, dict) else {"decoded_payload": decoded}
    except Exception as e:
        return {"decode_error": str(e)}


def sanitize_token_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
    return {
        "iss": payload.get("iss"),
        "sub": payload.get("sub"),
        "name": payload.get("name"),
        "nbf": payload.get("nbf"),
        "exp": payload.get("exp"),
        "room": video.get("room"),
        "roomJoin": video.get("roomJoin"),
        "canPublishData": video.get("canPublishData"),
        "has_metadata": bool(payload.get("metadata")),
    }


def collect_probe_runtime_fingerprint() -> Dict[str, Any]:
    versions: Dict[str, str] = {}
    for pkg in ("livekit", "livekit-api", "livekit-agents"):
        try:
            versions[pkg] = importlib_metadata.version(pkg)
        except Exception as e:
            versions[pkg] = f"missing:{e}"
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "packages": versions,
    }


def is_probe_auth_header_error(message: str) -> bool:
    return "missing authorization header" in (message or "").lower()


def is_provider_rate_limit_error(message: str) -> bool:
    m = (message or "").lower()
    return "rate limit" in m or "429" in m or "tpm" in m or "rate_limit_exceeded" in m


def classify_runtime_error(error: Optional[str], path: str) -> Optional[str]:
    if not error:
        return None
    if is_provider_rate_limit_error(error):
        return "provider_rate_limit"
    if path == "flutter_triggered" and is_probe_auth_header_error(error):
        return "probe_runtime_error"
    return "integration_error" if path == "flutter_triggered" else "logic_error"


def write_probe_diag_report(
    *,
    token_server_url: str,
    room_name: str,
    participant_name: str,
    token_resp: Optional[Dict[str, Any]],
    error: str,
) -> str:
    payload = {
        "probe": "livekit_flutter_client_connect",
        "token_server_url": token_server_url,
        "room_name": room_name,
        "participant_name": participant_name,
        "fingerprint": collect_probe_runtime_fingerprint(),
        "token_server_response": {
            "has_token": bool((token_resp or {}).get("token")),
            "url": (token_resp or {}).get("url"),
        },
        "token_payload": sanitize_token_payload(
            decode_jwt_payload(str((token_resp or {}).get("token") or ""))
        ),
        "result": {
            "ok": False,
            "error_code": "probe_auth_header_missing" if is_probe_auth_header_error(error) else "probe_connect_error",
            "error": error,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    PROBE_DIAG_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROBE_DIAG_REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(PROBE_DIAG_REPORT_PATH)


def apply_provider_profile(profile: str) -> Dict[str, Any]:
    chosen = (profile or "auto").strip().lower()
    if chosen not in {"auto", "deepseek", "groq", "nvidia", "perplexity"}:
        chosen = "auto"
    if chosen == "auto":
        chosen = (
            "nvidia"
            if os.getenv("NVIDIA_API_KEY")
            else "deepseek"
            if os.getenv("DEEPSEEK_API_KEY")
            else "perplexity"
            if os.getenv("PERPLEXITY_API_KEY")
            else "groq"
        )

    model_map = {
        "deepseek": "deepseek-chat",
        "groq": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        "nvidia": os.getenv("LLM_MODEL", "meta/llama-3.1-70b-instruct"),
        "perplexity": os.getenv("LLM_MODEL", "sonar-pro"),
    }
    provider = chosen
    model = model_map[chosen]
    env_updates = {
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model,
        "MAYA_CHAT_LLM_PROVIDER": provider,
        "MAYA_CHAT_LLM_MODEL": model,
        "MAYA_PLANNER_LLM_PROVIDER": provider,
        "MAYA_PLANNER_LLM_MODEL": model,
        "MAYA_TOOL_LLM_PROVIDER": provider,
        "MAYA_TOOL_LLM_MODEL": model,
        "MAYA_WORKER_LLM_PROVIDER": provider,
        "MAYA_WORKER_LLM_MODEL": model,
    }
    os.environ.update(env_updates)
    return {"provider_profile": profile, "resolved_provider": provider, "resolved_model": model}


def parse_log_ts_ms(event: Dict[str, Any]) -> Optional[int]:
    raw = event.get("ts_ms")
    if isinstance(raw, (int, float)):
        return int(raw)
    ts = event.get("ts")
    if isinstance(ts, str):
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return int(parsed.timestamp() * 1000)
        except Exception:
            return None
    return None


class LiveKitFlutterClient:
    """
    Flutter-equivalent text path probe over LiveKit data channel (`lk.chat`).
    """

    def __init__(
        self,
        token_server_url: str,
        room_name: Optional[str] = None,
        participant_name: str = "phase-gatekeeper-probe",
        connect_timeout_s: float = 45.0,
    ) -> None:
        self.token_server_url = token_server_url.rstrip("/")
        self.room_name = room_name or f"phase4-gate-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        self.participant_name = participant_name
        self.connect_timeout_s = connect_timeout_s
        self._response_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._room: Any = None
        self._connected = False
        self._audio_source: Any = None
        self._audio_track_published = False
        self.last_observation: Dict[str, Any] = {}
        self.last_probe_runtime_status: Dict[str, Any] = {
            "status": "not_attempted",
            "message": None,
            "diagnostic_report": None,
            "fingerprint": None,
        }

    @staticmethod
    def _extract_event_text(event: Dict[str, Any]) -> str:
        return str(
            event.get("content")
            or event.get("display_text")
            or event.get("content_preview")
            or event.get("voice_text")
            or ""
        ).strip()

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self._connected:
            return

        from livekit import rtc

        token_payload = {
            "roomName": self.room_name,
            "participantName": self.participant_name,
            "metadata": {"probe": "phase_gatekeeper_flutter"},
        }
        token_resp = await asyncio.to_thread(
            post_json,
            f"{self.token_server_url}/token",
            token_payload,
            self.connect_timeout_s,
        )
        token = token_resp.get("token")
        livekit_url = token_resp.get("url")
        if not token or not livekit_url:
            raise RuntimeError("Token server response missing token/url")

        room = rtc.Room()

        @room.on("data_received")
        def _on_data_received(packet: Any) -> None:
            try:
                topic = getattr(packet, "topic", None)
                data = bytes(getattr(packet, "data", b""))
                if topic != "chat_events":
                    return
                raw = data.decode("utf-8", errors="ignore")
                event = json.loads(raw) if raw else {}
                if event.get("type") in {
                    "assistant_final",
                    "transcription_agent_final",
                    "tool_execution",
                    "tool_execution_started",
                    "tool_execution_finished",
                }:
                    self._response_queue.put_nowait(event)
            except Exception:
                return

        try:
            await room.connect(livekit_url, token)
        except Exception as e:
            err = str(e)
            diag_path = None
            status = "connect_error"
            if is_probe_auth_header_error(err):
                status = "probe_auth_header_missing"
                diag_path = write_probe_diag_report(
                    token_server_url=self.token_server_url,
                    room_name=self.room_name,
                    participant_name=self.participant_name,
                    token_resp=token_resp,
                    error=err,
                )
            self.last_probe_runtime_status = {
                "status": status,
                "message": err,
                "diagnostic_report": diag_path,
                "fingerprint": collect_probe_runtime_fingerprint(),
            }
            raise
        self._room = room
        self.last_probe_runtime_status = {
            "status": "connected",
            "message": None,
            "diagnostic_report": None,
            "fingerprint": collect_probe_runtime_fingerprint(),
        }

        wait_until = time.perf_counter() + self.connect_timeout_s
        while time.perf_counter() < wait_until:
            if len(room.remote_participants) > 0:
                self._connected = True
                return
            await asyncio.sleep(0.25)
        raise RuntimeError(
            f"LiveKit room connected but no agent participant joined within {self.connect_timeout_s:.0f}s"
        )

    async def close(self) -> None:
        if self._room is None:
            return
        try:
            await self._room.disconnect()
        except Exception:
            pass
        if self._audio_source is not None:
            try:
                await self._audio_source.aclose()
            except Exception:
                pass
            self._audio_source = None
        self._audio_track_published = False
        self._room = None
        self._connected = False

    async def _ensure_mic_track(self) -> None:
        if self._room is None:
            raise RuntimeError("LiveKit room unavailable for voice probe")
        if self._audio_track_published and self._audio_source is not None:
            return

        from livekit import rtc

        sample_rate = int(os.getenv("GATEKEEPER_VOICE_SAMPLE_RATE", "24000"))
        channels = int(os.getenv("GATEKEEPER_VOICE_CHANNELS", "1"))
        self._audio_source = rtc.AudioSource(sample_rate=sample_rate, num_channels=channels)
        local_track = rtc.LocalAudioTrack.create_audio_track("gatekeeper_probe_mic", self._audio_source)
        opts = rtc.TrackPublishOptions()
        opts.source = rtc.TrackSource.SOURCE_MICROPHONE
        await self._room.local_participant.publish_track(local_track, opts)
        self._audio_track_published = True

    async def _synth_prompt_pcm(self, prompt: str) -> bytes:
        from livekit.agents.utils import codecs

        voice = os.getenv("GATEKEEPER_VOICE_TTS", "en-US-JennyNeural")
        sample_rate = int(os.getenv("GATEKEEPER_VOICE_SAMPLE_RATE", "24000"))
        channels = int(os.getenv("GATEKEEPER_VOICE_CHANNELS", "1"))
        communicate = edge_tts.Communicate(prompt, voice=voice)
        decoder = codecs.AudioStreamDecoder(
            sample_rate=sample_rate,
            num_channels=channels,
            format="audio/mpeg",
        )
        pcm = bytearray()

        async def _decode_task() -> None:
            async for frame in decoder:
                pcm.extend(frame.data.tobytes())

        task = asyncio.create_task(_decode_task())
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                decoder.push(chunk["data"])
        decoder.end_input()
        await task
        return bytes(pcm)

    async def _publish_pcm_audio(self, pcm: bytes) -> None:
        from livekit import rtc

        if self._audio_source is None:
            raise RuntimeError("Audio source not initialized")
        sample_rate = int(os.getenv("GATEKEEPER_VOICE_SAMPLE_RATE", "24000"))
        channels = int(os.getenv("GATEKEEPER_VOICE_CHANNELS", "1"))
        frame_ms = int(os.getenv("GATEKEEPER_VOICE_FRAME_MS", "20"))
        samples_per_frame = int(sample_rate * frame_ms / 1000)
        bytes_per_frame = samples_per_frame * channels * 2

        for i in range(0, len(pcm), bytes_per_frame):
            chunk = pcm[i : i + bytes_per_frame]
            if len(chunk) < (2 * channels):
                continue
            samples = len(chunk) // (2 * channels)
            frame = rtc.AudioFrame(chunk, sample_rate, channels, samples)
            await self._audio_source.capture_frame(frame)
            await asyncio.sleep(samples / sample_rate)
        await self._audio_source.wait_for_playout()

    async def send_and_wait(self, prompt: str, timeout_s: float = 25.0) -> Tuple[str, float, Optional[str]]:
        if not self._connected or self._room is None:
            return "", 0.0, "LiveKit client not connected"

        while True:
            try:
                self._response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        t0 = time.perf_counter()
        observed_tools: List[str] = []
        try:
            await self._room.local_participant.publish_data(
                prompt.encode("utf-8"),
                topic="lk.chat",
            )
            wait_until = time.perf_counter() + timeout_s
            while time.perf_counter() < wait_until:
                event = await asyncio.wait_for(
                    self._response_queue.get(),
                    timeout=max(0.05, wait_until - time.perf_counter()),
                )
                event_type = str(event.get("type") or "")
                if event_type in {"tool_execution", "tool_execution_started", "tool_execution_finished"}:
                    tool_name = str(event.get("tool") or event.get("tool_name") or "").strip()
                    if tool_name:
                        observed_tools.append(tool_name)
                    continue

                if event_type not in {"assistant_final", "transcription_agent_final"}:
                    continue

                response = self._extract_event_text(event)
                self.last_observation = {
                    "tool_event_observed": bool(observed_tools),
                    "observed_tools": observed_tools,
                    "response_event_type": event_type,
                }
                if response:
                    return response, (time.perf_counter() - t0) * 1000.0, None
                return "", (time.perf_counter() - t0) * 1000.0, "assistant_final missing content"
            self.last_observation = {
                "tool_event_observed": bool(observed_tools),
                "observed_tools": observed_tools,
                "response_event_type": None,
            }
            return "", (time.perf_counter() - t0) * 1000.0, f"Timed out after {timeout_s:.0f}s"
        except asyncio.TimeoutError:
            return "", (time.perf_counter() - t0) * 1000.0, f"Timed out after {timeout_s:.0f}s"
        except Exception as e:
            return "", (time.perf_counter() - t0) * 1000.0, str(e)

    async def send_voice_and_wait(
        self,
        prompt: str,
        timeout_s: float = 30.0,
    ) -> Tuple[str, float, Optional[str]]:
        if not self._connected or self._room is None:
            return "", 0.0, "LiveKit client not connected"

        while True:
            try:
                self._response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        t0 = time.perf_counter()
        observed_tools: List[str] = []
        try:
            await self._ensure_mic_track()
            pcm = await self._synth_prompt_pcm(prompt)
            await self._publish_pcm_audio(pcm)
            wait_until = time.perf_counter() + timeout_s
            while time.perf_counter() < wait_until:
                event = await asyncio.wait_for(
                    self._response_queue.get(),
                    timeout=max(0.05, wait_until - time.perf_counter()),
                )
                event_type = str(event.get("type") or "")
                if event_type in {"tool_execution", "tool_execution_started", "tool_execution_finished"}:
                    tool_name = str(event.get("tool") or event.get("tool_name") or "").strip()
                    if tool_name:
                        observed_tools.append(tool_name)
                    continue

                if event_type not in {"assistant_final", "transcription_agent_final"}:
                    continue

                response = self._extract_event_text(event)
                self.last_observation = {
                    "tool_event_observed": bool(observed_tools),
                    "observed_tools": observed_tools,
                    "response_event_type": event_type,
                }
                if response:
                    return response, (time.perf_counter() - t0) * 1000.0, None
                return "", (time.perf_counter() - t0) * 1000.0, "assistant_final missing content"
            self.last_observation = {
                "tool_event_observed": bool(observed_tools),
                "observed_tools": observed_tools,
                "response_event_type": None,
            }
            return "", (time.perf_counter() - t0) * 1000.0, f"Timed out after {timeout_s:.0f}s"
        except asyncio.TimeoutError:
            return "", (time.perf_counter() - t0) * 1000.0, f"Timed out after {timeout_s:.0f}s"
        except Exception as e:
            return "", (time.perf_counter() - t0) * 1000.0, str(e)


class FlutterDesktopLogClient:
    """
    Real Flutter desktop app evidence reader.
    Reads append-only JSONL logs written by the Flutter app in gatekeeper mode.
    Prompts are entered manually in the app; this client observes user + assistant events.
    """

    def __init__(
        self,
        log_path: str,
        manual_mode: bool = True,
        command_path: Optional[str] = None,
    ) -> None:
        self.log_path = Path(log_path)
        self.manual_mode = manual_mode
        self.command_path = Path(command_path).expanduser() if command_path else None
        self._connected = False
        self._offset = 0
        self._events: List[Dict[str, Any]] = []
        self.last_observation: Dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self, timeout_s: float = 45.0) -> None:
        if self.command_path:
            self.command_path.parent.mkdir(parents=True, exist_ok=True)
            # Reset command stream at run start to avoid replaying stale prompts.
            self.command_path.write_text("", encoding="utf-8")
        wait_until = time.perf_counter() + timeout_s
        while time.perf_counter() < wait_until:
            if self.log_path.exists():
                # Start at EOF to avoid matching stale events from older sessions.
                self._offset = self.log_path.stat().st_size
                self._connected = True
                return
            await asyncio.sleep(0.25)
        raise RuntimeError(f"Flutter desktop gatekeeper log not found: {self.log_path}")

    async def close(self) -> None:
        self._connected = False

    def _dispatch_prompt_command(self, prompt: str) -> None:
        if self.command_path is None:
            return
        payload = {
            "type": "send_prompt",
            "id": uuid.uuid4().hex,
            "prompt": prompt,
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        with self.command_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def _latest_connection_status(self) -> Optional[str]:
        active_event_types = {
            "chat_event_received",
            "assistant_final",
            "assistant_delta",
            "user_message_sent",
            "autopilot_prompt_sent",
            "transcription_agent_partial",
            "transcription_agent_final",
            "tool_execution_started",
            "tool_execution_finished",
        }
        saw_activity = False
        # Check in-memory buffered events first.
        for ev in reversed(self._events):
            ev_type = str(ev.get("event_type") or "")
            if ev_type in active_event_types:
                saw_activity = True
            if ev_type == "session_connection_state":
                status = str(ev.get("status") or "").strip().lower()
                if status:
                    return status

        # Fallback: inspect recent tail on disk in case we connected at EOF.
        if not self.log_path.exists():
            return None
        try:
            size = self.log_path.stat().st_size
            start = max(0, size - 128 * 1024)
            with self.log_path.open("r", encoding="utf-8", errors="ignore") as fh:
                fh.seek(start)
                chunk = fh.read()
            lines = chunk.splitlines()
            if start > 0 and lines:
                lines = lines[1:]  # drop possible partial line
            for line in reversed(lines):
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if isinstance(ev, dict):
                    ev_type = str(ev.get("event_type") or "")
                    if ev_type in active_event_types:
                        saw_activity = True
                    if ev_type == "session_connection_state":
                        status = str(ev.get("status") or "").strip().lower()
                        if status:
                            return status
        except Exception:
            return "connected" if saw_activity else None
        if saw_activity:
            return "connected"
        return None

    def _poll_events(self) -> None:
        if not self.log_path.exists():
            return
        with self.log_path.open("r", encoding="utf-8", errors="ignore") as fh:
            fh.seek(self._offset)
            chunk = fh.read()
            self._offset = fh.tell()
        if not chunk:
            return
        for line in chunk.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    self._events.append(parsed)
            except Exception:
                continue

    async def _wait_for_event(
        self,
        predicate,
        timeout_s: float,
        start_index: int = 0,
        poll_s: float = 0.2,
    ) -> Tuple[Dict[str, Any], int]:
        idx = start_index
        wait_until = time.perf_counter() + timeout_s
        while time.perf_counter() < wait_until:
            self._poll_events()
            while idx < len(self._events):
                event = self._events[idx]
                idx += 1
                if predicate(event):
                    return event, idx
            await asyncio.sleep(poll_s)
        raise TimeoutError(f"Timed out after {timeout_s:.0f}s waiting for Flutter desktop log event")

    async def send_and_wait(self, prompt: str, timeout_s: float = 25.0) -> Tuple[str, float, Optional[str]]:
        if not self._connected:
            return "", 0.0, "FlutterDesktopLogClient not connected"

        # Guard against early prompts before LiveKit session is fully connected.
        self._poll_events()
        current_status = self._latest_connection_status()
        if current_status != "connected":
            try:
                _, _ = await self._wait_for_event(
                    lambda ev: ev.get("event_type") == "session_connection_state"
                    and str(ev.get("status") or "").strip().lower() == "connected",
                    timeout_s=min(timeout_s, 20.0),
                    start_index=max(0, len(self._events) - 1),
                )
            except TimeoutError:
                return "", 0.0, "Flutter session not connected; waiting for connected state timed out"

        start_idx = len(self._events)
        print(
            f"[FLUTTER_DESKTOP] Enter this prompt in the Flutter Linux app chat, then wait for the response:\n"
            f"  {prompt}",
            flush=True,
        )
        if self.command_path is not None:
            self._dispatch_prompt_command(prompt)
            print(
                f"[FLUTTER_DESKTOP] Dispatched prompt command via {self.command_path}",
                flush=True,
            )

        normalized_prompt = normalize_text(prompt)
        normalized_prompt_loose = re.sub(r"[^a-z0-9\s]", " ", normalized_prompt)
        normalized_prompt_loose = " ".join(normalized_prompt_loose.split())

        def _matches_prompt_content(content: str) -> bool:
            normalized_content = normalize_text(content)
            if normalized_content == normalized_prompt:
                return True
            normalized_content_loose = re.sub(r"[^a-z0-9\s]", " ", normalized_content)
            normalized_content_loose = " ".join(normalized_content_loose.split())
            return normalized_content_loose == normalized_prompt_loose

        def _is_user_prompt(ev: Dict[str, Any]) -> bool:
            if ev.get("event_type") != "user_message_sent":
                return False
            content = str(ev.get("content") or ev.get("content_preview") or "")
            return _matches_prompt_content(content)

        matched_user_prompt = True
        observed_user_prompt = ""
        try:
            user_event, idx_after_user = await self._wait_for_event(
                _is_user_prompt,
                timeout_s=timeout_s,
                start_index=start_idx,
            )
            observed_user_prompt = str(
                user_event.get("content") or user_event.get("content_preview") or ""
            ).strip()
        except TimeoutError as e:
            # Manual mode fallback: accept first user_message_sent after start even if prompt differs.
            if self.manual_mode:
                try:
                    user_event, idx_after_user = await self._wait_for_event(
                        lambda ev: ev.get("event_type") == "user_message_sent",
                        timeout_s=min(8.0, timeout_s),
                        start_index=start_idx,
                    )
                    matched_user_prompt = False
                    observed_user_prompt = str(
                        user_event.get("content") or user_event.get("content_preview") or ""
                    ).strip()
                    mismatch_msg = (
                        "Manual prompt mismatch for Flutter desktop run. "
                        f"Expected: {prompt!r}. Observed: {observed_user_prompt!r}."
                    )
                    self.last_observation = {
                        "matched_user_prompt": False,
                        "observed_user_prompt": observed_user_prompt,
                        "expected_prompt": prompt,
                        "observed_tools": [],
                        "duplicate_final_count": 0,
                        "tool_event_observed": False,
                    }
                    return "", 0.0, mismatch_msg
                except TimeoutError:
                    self.last_observation = {
                        "matched_user_prompt": False,
                        "observed_user_prompt": "",
                        "expected_prompt": prompt,
                        "observed_tools": [],
                        "duplicate_final_count": 0,
                        "tool_event_observed": False,
                    }
                    return "", 0.0, str(e)
            else:
                # Fallback: some UI paths only emit chat_events user_message; recover from that.
                self._poll_events()
                fallback_event = None
                fallback_idx = None
                for i in range(len(self._events) - 1, max(-1, len(self._events) - 500), -1):
                    ev = self._events[i]
                    if ev.get("event_type") != "chat_event_received":
                        continue
                    if str(ev.get("status") or "") != "user_message":
                        continue
                    content = str(ev.get("content") or ev.get("content_preview") or "")
                    if _matches_prompt_content(content):
                        fallback_event = ev
                        fallback_idx = i + 1
                        break
                if fallback_event is not None:
                    user_event = fallback_event
                    idx_after_user = fallback_idx or len(self._events)
                    observed_user_prompt = str(
                        user_event.get("content") or user_event.get("content_preview") or ""
                    ).strip()
                else:
                    self.last_observation = {
                        "matched_user_prompt": False,
                        "observed_user_prompt": "",
                        "expected_prompt": prompt,
                        "observed_tools": [],
                        "duplicate_final_count": 0,
                        "tool_event_observed": False,
                    }
                    return "", 0.0, str(e)

        user_ts_ms = parse_log_ts_ms(user_event) or int(time.time() * 1000)
        user_turn_id = user_event.get("turn_id")
        user_chat_event: Optional[Dict[str, Any]] = None
        # Prefer turn_id from chat_events user_message for precise correlation.
        def _is_chat_user_message(ev: Dict[str, Any]) -> bool:
            if ev.get("event_type") != "chat_event_received":
                return False
            if str(ev.get("status") or "") != "user_message":
                return False
            content = str(ev.get("content") or ev.get("content_preview") or "")
            normalized_content = normalize_text(content)
            if normalized_content != normalized_prompt:
                normalized_content_loose = re.sub(r"[^a-z0-9\\s]", " ", normalized_content)
                normalized_content_loose = " ".join(normalized_content_loose.split())
                if normalized_content_loose != normalized_prompt_loose:
                    return False
            ev_ts_ms = parse_log_ts_ms(ev)
            if ev_ts_ms is not None and user_ts_ms:
                # Allow chat_event_received to precede user_message_sent slightly.
                if ev_ts_ms < (user_ts_ms - 1500):
                    return False
            return True

        try:
            user_chat_event, idx_after_user = await self._wait_for_event(
                _is_chat_user_message,
                timeout_s=min(10.0, timeout_s),
                start_index=max(0, idx_after_user - 200),
            )
            if user_chat_event:
                user_turn_id = user_chat_event.get("turn_id") or user_turn_id
                chat_ts_ms = parse_log_ts_ms(user_chat_event)
                if chat_ts_ms is not None:
                    user_ts_ms = max(user_ts_ms, chat_ts_ms)
        except TimeoutError:
            # If chat_events user_message isn't observed, fall back to user_message_sent timing.
            pass

        tool_events: List[Dict[str, Any]] = []
        duplicate_final_count = 0
        assistant_final: Optional[Dict[str, Any]] = None
        transcription_final: Optional[Dict[str, Any]] = None
        transcription_final_seen_at: Optional[float] = None
        idx = idx_after_user
        wait_until = time.perf_counter() + timeout_s
        observed_turn_prompts: Dict[str, str] = {}

        while time.perf_counter() < wait_until:
            self._poll_events()
            while idx < len(self._events):
                ev = self._events[idx]
                idx += 1
                ev_type = str(ev.get("event_type") or "")
                ev_turn = ev.get("turn_id")
                ev_ts_ms = parse_log_ts_ms(ev)

                if ev_type == "chat_event_received" and str(ev.get("status") or "") == "user_message":
                    content = str(ev.get("content") or ev.get("content_preview") or "")
                    normalized_content = normalize_text(content)
                    if ev_turn and normalized_content:
                        observed_turn_prompts[ev_turn] = normalized_content
                    if user_turn_id is None and _is_chat_user_message(ev):
                        user_turn_id = ev_turn or user_turn_id
                        if ev_ts_ms is not None:
                            user_ts_ms = max(user_ts_ms, ev_ts_ms)

                if ev_type.startswith("tool_execution_") or (
                    ev_type == "chat_event_received" and str(ev.get("status") or "") == "tool_execution"
                ):
                    if user_turn_id and ev_turn and ev_turn != user_turn_id:
                        continue
                    if ev_ts_ms is not None and ev_ts_ms + 50 < user_ts_ms:
                        continue
                    tool_events.append(ev)

                if ev_type == "assistant_final":
                    if ev_ts_ms is not None and ev_ts_ms + 50 < user_ts_ms:
                        continue
                    ev_status = str(ev.get("status") or "")
                    if ev_status and ev_status not in {"rendered", "suppressed_duplicate"}:
                        continue
                    # Prefer same turn when available; otherwise first final after user event.
                    if user_turn_id and ev_turn and ev_turn != user_turn_id:
                        continue
                    if user_turn_id is None and ev_turn:
                        observed_prompt = observed_turn_prompts.get(ev_turn)
                        if observed_prompt and observed_prompt != normalized_prompt:
                            continue
                    if assistant_final is None:
                        assistant_final = ev
                    else:
                        same_turn = (assistant_final.get("turn_id") or None) == (ev_turn or None)
                        if same_turn:
                            duplicate_final_count += 1
                            # Keep the latest rendered final as canonical response.
                            assistant_final = ev
                elif ev_type == "transcription_agent_final":
                    if ev_ts_ms is not None and ev_ts_ms + 50 < user_ts_ms:
                        continue
                    if user_turn_id and ev_turn and ev_turn != user_turn_id:
                        continue
                    # Fallback when structured assistant_final is intentionally suppressed
                    # by live transcription dedupe logic.
                    if transcription_final is None:
                        transcription_final = ev
                        transcription_final_seen_at = time.perf_counter()
            if assistant_final is not None:
                grace_until = time.perf_counter() + 0.6
                while time.perf_counter() < grace_until:
                    self._poll_events()
                    while idx < len(self._events):
                        ev = self._events[idx]
                        idx += 1
                        ev_type = str(ev.get("event_type") or "")
                        if not (
                            ev_type.startswith("tool_execution_")
                            or (ev_type == "chat_event_received" and str(ev.get("status") or "") == "tool_execution")
                        ):
                            continue
                        ev_turn = ev.get("turn_id")
                        if user_turn_id and ev_turn and ev_turn != user_turn_id:
                            continue
                        ev_ts_ms = parse_log_ts_ms(ev)
                        if ev_ts_ms is not None and ev_ts_ms + 50 < user_ts_ms:
                            continue
                        tool_events.append(ev)
                    await asyncio.sleep(0.1)
                break
            if assistant_final is None and transcription_final is not None:
                # Give structured assistant_final a short grace window to arrive.
                if (time.perf_counter() - (transcription_final_seen_at or 0.0)) >= 1.5:
                    break
            await asyncio.sleep(0.2)

        if assistant_final is None and transcription_final is None:
            self.last_observation = {
                "matched_user_prompt": matched_user_prompt,
                "observed_user_prompt": observed_user_prompt,
                "expected_prompt": prompt,
                "observed_tools": [str(e.get("tool_name")) for e in tool_events if e.get("tool_name")],
                "duplicate_final_count": duplicate_final_count,
                "tool_event_observed": bool(tool_events),
            }
            return "", 0.0, f"Timed out after {timeout_s:.0f}s waiting for assistant_final in Flutter desktop log"

        resolved_final = assistant_final or transcription_final or {}

        final_ts_ms = parse_log_ts_ms(resolved_final) or int(time.time() * 1000)
        latency_ms = max(0.0, float(final_ts_ms - user_ts_ms))
        response = str(resolved_final.get("content") or resolved_final.get("content_preview") or "").strip()
        observed_tools = [str(e.get("tool_name")) for e in tool_events if e.get("tool_name")]

        self.last_observation = {
            "matched_user_prompt": matched_user_prompt,
            "observed_user_prompt": observed_user_prompt,
            "expected_prompt": prompt,
            "user_turn_id": user_turn_id,
            "assistant_turn_id": resolved_final.get("turn_id"),
            "observed_tools": observed_tools,
            "tool_event_observed": bool(tool_events),
            "duplicate_final_count": duplicate_final_count,
            "assistant_final_status": resolved_final.get("status"),
            "response_event_type": (
                "assistant_final" if assistant_final is not None else "transcription_agent_final"
            ),
        }
        if not response:
            return "", latency_ms, "assistant_final missing content in Flutter desktop log"
        return response, latency_ms, None


SEMANTIC_SYNONYMS = {
    "alarms": "reminder",
    "alarm": "reminder",
    "reminders": "reminder",
    "minute": "minutes",
    "mins": "minutes",
    "set": "create",
    "started": "create",
    "start": "create",
}

SEMANTIC_STOPWORDS = {
    "a",
    "an",
    "the",
    "i",
    "me",
    "my",
    "your",
    "you",
    "for",
    "to",
    "in",
    "on",
    "at",
    "of",
    "and",
    "or",
    "is",
    "it",
    "that",
    "this",
    "with",
    "please",
}


def normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def normalize_semantic_tokens(text: str) -> List[str]:
    compact = normalize_text(text)
    if not compact:
        return []
    cleaned = re.sub(r"[^a-z0-9\s]", " ", compact)
    tokens: List[str] = []
    for raw in cleaned.split():
        token = SEMANTIC_SYNONYMS.get(raw, raw)
        if token in SEMANTIC_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def semantic_match(a: str, b: str) -> bool:
    aa_tokens = normalize_semantic_tokens(a)
    bb_tokens = normalize_semantic_tokens(b)
    if not aa_tokens or not bb_tokens:
        return False

    aa = set(aa_tokens)
    bb = set(bb_tokens)
    overlap = len(aa & bb)
    overlap_ratio = overlap / max(1, min(len(aa), len(bb)))
    jaccard = overlap / max(1, len(aa | bb))

    if overlap_ratio >= 0.5:
        return True
    if jaccard >= 0.35:
        return True

    seq_ratio = difflib.SequenceMatcher(
        None,
        " ".join(aa_tokens),
        " ".join(bb_tokens),
    ).ratio()
    if seq_ratio >= 0.42:
        return True

    numeric_a = {tok for tok in aa if tok.isdigit()}
    numeric_b = {tok for tok in bb if tok.isdigit()}
    intent_markers = {"reminder", "task", "schedule", "time", "weather", "search", "summary"}
    if numeric_a and numeric_b and (numeric_a & numeric_b) and ((aa & bb) & intent_markers):
        return True

    return False


def formatting_match(a: str, b: str) -> bool:
    return abs(len((a or "").strip()) - len((b or "").strip())) <= 180


def classify_response_failure(text: str) -> Optional[str]:
    normalized = normalize_text(text)
    if not normalized:
        return "empty_response"
    if is_provider_rate_limit_error(normalized):
        return "provider_rate_limit"
    failure_markers = [
        "i hit an internal issue while handling that",
        "sorry, i encountered an issue processing your request",
        "please try once more",
        "please try again",
        "cannot complete operation",
    ]
    if any(marker in normalized for marker in failure_markers):
        return "runtime_failure_response"
    if normalized.startswith("failed to "):
        return "tool_failure_response"
    return None


def summarize_text(text: str, max_len: int = 180) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


def load_example_suite(suite_file: Optional[str]) -> List[Dict[str, Any]]:
    if not suite_file:
        return [dict(item) for item in EXAMPLES]
    path = Path(suite_file)
    if not path.exists():
        raise FileNotFoundError(f"Suite file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Suite file must be a JSON object")
    examples = payload.get("examples")
    if not isinstance(examples, list):
        raise ValueError("Suite file must contain an 'examples' list")
    normalized: List[Dict[str, Any]] = []
    for i, raw in enumerate(examples, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Example #{i} must be an object")
        item = dict(raw)
        for field in ("id", "prompt", "category", "difficulty"):
            if not str(item.get(field) or "").strip():
                raise ValueError(f"Example #{i} missing required field '{field}'")
        item["id"] = str(item["id"]).strip()
        item["prompt"] = str(item["prompt"]).strip()
        item["category"] = str(item["category"]).strip()
        item["difficulty"] = str(item["difficulty"]).strip().upper()
        item["scenario"] = str(item.get("scenario") or item["id"]).strip()
        normalized.append(item)
    return normalized


async def run_direct(
    prompt: str,
    timeout_s: float = 25.0,
    user_id: str = "console_user",
) -> Tuple[str, float, Optional[str]]:
    from core.runtime.global_agent import GlobalAgentContainer

    t0 = time.perf_counter()
    try:
        if not GlobalAgentContainer._initialized:
            await GlobalAgentContainer.initialize()
        orch = GlobalAgentContainer.get_orchestrator()
        if orch is None:
            return "", (time.perf_counter() - t0) * 1000.0, "Orchestrator not initialized"
        response = await asyncio.wait_for(
            orch.handle_message(prompt, user_id=user_id),
            timeout=timeout_s,
        )
        if hasattr(response, "display_text"):
            response_text = str(getattr(response, "display_text") or "").strip()
            if response_text:
                return response_text, (time.perf_counter() - t0) * 1000.0, None
            fallback_voice = str(getattr(response, "voice_text", "") or "").strip()
            if fallback_voice:
                return fallback_voice, (time.perf_counter() - t0) * 1000.0, None
        if isinstance(response, dict):
            response_text = str(
                response.get("display_text")
                or response.get("content")
                or response.get("text")
                or ""
            ).strip()
            if response_text:
                return response_text, (time.perf_counter() - t0) * 1000.0, None
        return str(response or ""), (time.perf_counter() - t0) * 1000.0, None
    except asyncio.TimeoutError:
        return "", (time.perf_counter() - t0) * 1000.0, f"Timed out after {timeout_s:.0f}s"
    except Exception as e:
        return "", (time.perf_counter() - t0) * 1000.0, str(e)


async def run_flutter(
    prompt: str,
    flutter_mode: str,
    flutter_api_url: Optional[str],
    livekit_client: Optional[LiveKitFlutterClient],
    desktop_client: Optional[FlutterDesktopLogClient],
    allow_simulated_flutter: bool,
    channel: str = "chat",
    timeout_s: float = 25.0,
) -> Tuple[str, float, Optional[str], bool]:
    """
    Returns: response, latency_ms, error, used_simulation
    """
    mode = (flutter_mode or "livekit").strip().lower()

    if mode == "http":
        if not flutter_api_url:
            return "", 0.0, "flutter_mode=http requires --flutter-api-url", False
        t0 = time.perf_counter()
        try:
            payload = json.dumps({"message": prompt}).encode("utf-8")
            req = request.Request(
                flutter_api_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw) if raw.strip().startswith("{") else {"response": raw}
            response = str(data.get("response") or data.get("message") or raw)
            return response, (time.perf_counter() - t0) * 1000.0, None, False
        except Exception as e:
            return "", (time.perf_counter() - t0) * 1000.0, str(e), False

    if mode == "livekit":
        if livekit_client is None:
            return "", 0.0, "flutter_mode=livekit requires initialized LiveKit client", False
        if channel == "voice":
            response, latency_ms, error = await livekit_client.send_voice_and_wait(
                prompt,
                timeout_s=max(timeout_s, 30.0),
            )
        else:
            response, latency_ms, error = await livekit_client.send_and_wait(prompt, timeout_s=timeout_s)
        return response, latency_ms, error, False

    if mode == "linux-desktop":
        if desktop_client is None:
            return "", 0.0, "flutter_mode=linux-desktop requires initialized FlutterDesktopLogClient", False
        response, latency_ms, error = await desktop_client.send_and_wait(prompt, timeout_s=timeout_s)
        return response, latency_ms, error, False

    if mode != "simulated":
        return "", 0.0, f"Unsupported flutter mode '{flutter_mode}'", False

    if not allow_simulated_flutter:
        return "", 0.0, "flutter_mode=simulated requires --allow-simulated-flutter", False

    from core.runtime.global_agent import GlobalAgentContainer

    t0 = time.perf_counter()
    try:
        if not GlobalAgentContainer._initialized:
            await GlobalAgentContainer.initialize()
        orch = GlobalAgentContainer.get_orchestrator()
        response = await asyncio.wait_for(
            orch.handle_message(prompt, user_id="livekit:flutter_tester"),
            timeout=timeout_s,
        )
        return str(response or ""), (time.perf_counter() - t0) * 1000.0, None, True
    except asyncio.TimeoutError:
        return "", (time.perf_counter() - t0) * 1000.0, f"Timed out after {timeout_s:.0f}s", True
    except Exception as e:
        return "", (time.perf_counter() - t0) * 1000.0, str(e), True


def _load_prompt_overrides(path: Optional[str]) -> Dict[str, List[str]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            out: Dict[str, List[str]] = {}
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, list):
                    out[k] = [str(x) for x in v if str(x).strip()]
            # Preserve special include/exclude directives if provided.
            for key in ("__include_families", "__exclude_families"):
                raw = data.get(key)
                if isinstance(raw, list):
                    out[key] = [str(x).strip() for x in raw if str(x).strip()]
            return out
    except Exception:
        pass
    # Fallback: newline-delimited prompts assigned to a single family.
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    return {"custom": lines} if lines else {}


async def run_tool_capability_matrix_suite(
    *,
    flutter_mode: str,
    flutter_api_url: Optional[str],
    livekit_client: Optional[LiveKitFlutterClient],
    desktop_client: Optional[FlutterDesktopLogClient],
    allow_simulated_flutter: bool,
    prompt_overrides: Optional[Dict[str, List[str]]],
    timeout_s: float,
    inter_prompt_delay_s: float,
) -> Dict[str, Any]:
    families_payload = []
    all_results = []
    overrides = prompt_overrides or {}
    include_families = {
        name.strip() for name in (overrides.get("__include_families") or []) if str(name).strip()
    }
    exclude_families = {
        name.strip() for name in (overrides.get("__exclude_families") or []) if str(name).strip()
    }

    for family_def in TOOL_CAPABILITY_FAMILIES:
        family = str(family_def["family"])
        if include_families and family not in include_families:
            continue
        if family in exclude_families:
            continue
        prompts = overrides.get(family) or [str(p) for p in family_def.get("prompts", [])]
        expect_tool_event = bool(family_def.get("expect_tool_event", False))
        family_results = []
        for prompt in prompts[:3]:
            response, latency_ms, error, _ = await run_flutter(
                prompt,
                flutter_mode=flutter_mode,
                flutter_api_url=flutter_api_url,
                livekit_client=livekit_client,
                desktop_client=desktop_client,
                allow_simulated_flutter=allow_simulated_flutter,
                timeout_s=timeout_s,
            )
            if flutter_mode == "livekit":
                obs = dict(getattr(livekit_client, "last_observation", {})) if livekit_client is not None else {}
            else:
                obs = dict(getattr(desktop_client, "last_observation", {})) if desktop_client is not None else {}
            observed_tools = [str(t) for t in (obs.get("observed_tools") or []) if str(t).strip()]
            duplicate_final_count = int(obs.get("duplicate_final_count") or 0)
            tool_event_observed = bool(obs.get("tool_event_observed"))
            passed = bool(response.strip()) and error is None
            if flutter_mode == "linux-desktop" and expect_tool_event:
                passed = passed and tool_event_observed
            if flutter_mode == "linux-desktop" and not expect_tool_event:
                passed = passed and (not tool_event_observed)
            if flutter_mode == "linux-desktop":
                passed = passed and duplicate_final_count == 0

            item = {
                "family": family,
                "prompt": prompt,
                "response": response,
                "latency_ms": latency_ms,
                "error": error,
                "passed": passed,
                "expect_tool_event": expect_tool_event,
                "tool_event_observed": tool_event_observed,
                "observed_tools": observed_tools,
                "duplicate_final_count": duplicate_final_count,
            }
            family_results.append(item)
            all_results.append(item)
            if inter_prompt_delay_s > 0:
                await asyncio.sleep(inter_prompt_delay_s)

        pass_count = sum(1 for r in family_results if r["passed"])
        required_pass_count = max(1, min(2, len(family_results)))
        family_passed = pass_count >= required_pass_count
        if family in {"task_status", "recovery_clarification"}:
            if any(bool(r.get("tool_event_observed")) for r in family_results):
                family_passed = False
        family_pass_rate = (pass_count / len(family_results)) if family_results else 0.0
        families_payload.append(
            {
                "family": family,
                "expect_tool_event": expect_tool_event,
                "results": family_results,
                "family_pass_rate": family_pass_rate,
                "family_passed": family_passed,
                "required_pass_count": required_pass_count,
            }
        )

    total = len(all_results)
    passed_total = sum(1 for r in all_results if r["passed"])
    tool_expected_total = sum(1 for r in all_results if r["expect_tool_event"])
    tool_expected_hits = sum(
        1 for r in all_results if r["expect_tool_event"] and bool(r["tool_event_observed"])
    )
    unique_tools = sorted({tool for r in all_results for tool in r.get("observed_tools", []) if tool})
    cleanup_prompt = "close any apps, tabs, or media opened during this validation run"
    cleanup_response, cleanup_latency_ms, cleanup_error, _ = await run_flutter(
        cleanup_prompt,
        flutter_mode=flutter_mode,
        flutter_api_url=flutter_api_url,
        livekit_client=livekit_client,
        desktop_client=desktop_client,
        allow_simulated_flutter=allow_simulated_flutter,
        channel="chat",
        timeout_s=max(timeout_s, 20.0),
    )

    return {
        "enabled": True,
        "mode": flutter_mode,
        "families": families_payload,
        "summary": {
            "families_total": len(families_payload),
            "variants_total": total,
            "variant_pass_rate": (passed_total / total) if total else 0.0,
            "family_pass_rate": (
                sum(1 for f in families_payload if f.get("family_passed")) / len(families_payload)
                if families_payload
                else 0.0
            ),
            "unique_tool_names_invoked": unique_tools,
            "tool_selection_consistency": (
                (tool_expected_hits / tool_expected_total) if tool_expected_total else None
            ),
            "planner_vs_direct_tool_routing_accuracy": (
                (tool_expected_hits / tool_expected_total) if tool_expected_total else None
            ),
            "cleanup_prompt": cleanup_prompt,
            "cleanup_error": cleanup_error,
            "cleanup_latency_ms": cleanup_latency_ms,
            "cleanup_response": summarize_text(cleanup_response, max_len=240),
        },
    }


def check_structural() -> List[StructuralCheck]:
    checks: List[StructuralCheck] = []

    missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
    checks.append(
        StructuralCheck(
            name="required_files",
            passed=not missing,
            details="OK" if not missing else f"Missing files: {missing}",
        )
    )

    todo_hits = []
    for p in REQUIRED_FILES:
        if not p.exists():
            continue
        content = p.read_text(encoding="utf-8", errors="ignore")
        if "TODO" in content:
            todo_hits.append(p.name)
    checks.append(
        StructuralCheck(
            name="phase_scope_todos",
            passed=not todo_hits,
            details="No TODOs" if not todo_hits else f"TODO present in: {todo_hits}",
        )
    )

    try:
        from core.tasks.planning_engine import PlanningEngine  # noqa: F401
        from core.tasks.task_worker import TaskWorker  # noqa: F401
        checks.append(StructuralCheck("critical_imports", True, "Imports OK"))
    except Exception as e:
        checks.append(StructuralCheck("critical_imports", False, f"Import failed: {e}"))

    return checks


def p95(values: List[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    idx = int(round(0.95 * (len(ordered) - 1)))
    return ordered[idx]


async def run_gatekeeper(
    flutter_mode: str,
    flutter_api_url: Optional[str],
    token_server_url: str,
    livekit_room: Optional[str],
    livekit_participant: str,
    livekit_connect_timeout_s: float,
    desktop_log_path: Optional[str],
    desktop_manual: bool,
    desktop_prompt_file: Optional[str],
    desktop_command_path: Optional[str],
    allow_simulated_flutter: bool,
    provider_profile: str,
    run_tool_capability_matrix: bool,
    suite_file: Optional[str],
    difficulty_levels: int,
    run_voice_suite: bool,
    run_chat_suite: bool,
    request_timeout_s: float,
    inter_example_delay_s: float,
) -> Dict[str, Any]:
    examples = load_example_suite(suite_file)
    provider_profile_info = apply_provider_profile(provider_profile)
    structural = check_structural()

    direct_runs: List[ExampleRun] = []
    flutter_chat_runs: List[ExampleRun] = []
    flutter_voice_runs: List[ExampleRun] = []
    chat_parity_results: List[ExampleParity] = []
    voice_parity_results: List[ExampleParity] = []
    run_nonce = uuid.uuid4().hex[:8]

    used_simulated_flutter = False
    mode = (flutter_mode or "livekit").strip().lower()
    livekit_client: Optional[LiveKitFlutterClient] = None
    desktop_client: Optional[FlutterDesktopLogClient] = None
    integration_boot_error: Optional[str] = None
    probe_runtime_status: Dict[str, Any] = {
        "status": "not_attempted",
        "message": None,
        "diagnostic_report": None,
        "fingerprint": None,
    }
    direct_user_id = "console_user"
    active_scenario: Optional[str] = None
    tool_capability_matrix: Dict[str, Any] = {
        "enabled": False,
        "mode": mode,
        "results": [],
        "summary": {},
    }

    if mode in {"livekit", "linux-desktop"}:
        health_ok, health_msg = check_health(f"{token_server_url.rstrip('/')}/health")
        structural.append(
            StructuralCheck(
                name="token_server_health",
                passed=health_ok,
                details=health_msg if health_ok else f"Token server unavailable: {health_msg}",
            )
        )
        if not health_ok:
            integration_boot_error = "LiveKit/bootstrap skipped: token server health check failed"

    if mode == "http":
        if not flutter_api_url:
            integration_boot_error = "flutter_mode=http requires --flutter-api-url"
    elif mode == "simulated":
        if not allow_simulated_flutter:
            integration_boot_error = "flutter_mode=simulated requires --allow-simulated-flutter"
    elif mode == "livekit":
        # Supported probe/diagnostic mode; bootstrap happens per-example below.
        pass
    elif mode == "linux-desktop":
        if not desktop_log_path:
            integration_boot_error = "flutter_mode=linux-desktop requires --desktop-log-path"
        elif not desktop_manual and not desktop_prompt_file and not desktop_command_path:
            integration_boot_error = (
                "flutter_mode=linux-desktop requires --desktop-manual, --desktop-command-path, "
                "and/or --desktop-prompt-file"
            )
    else:
        integration_boot_error = f"Unsupported flutter_mode={flutter_mode}"

    try:
        if not integration_boot_error and mode == "linux-desktop":
            desktop_client = FlutterDesktopLogClient(
                log_path=str(desktop_log_path),
                manual_mode=desktop_manual,
                command_path=desktop_command_path,
            )
            try:
                await desktop_client.connect(timeout_s=livekit_connect_timeout_s)
                structural.append(
                    StructuralCheck(
                        name="flutter_desktop_log_ready",
                        passed=True,
                        details=str(desktop_log_path),
                    )
                )
            except Exception as e:
                integration_boot_error = f"Flutter desktop log bootstrap failed: {e}"
                structural.append(
                    StructuralCheck(
                        name="flutter_desktop_log_ready",
                        passed=False,
                        details=str(e),
                    )
                )

        for idx, example in enumerate(examples):
            scenario = str(example.get("scenario") or example["id"])
            scenario_participant = build_scenario_participant(
                livekit_participant,
                f"{scenario}-{run_nonce}",
            )
            direct_user_id = (
                f"livekit:{scenario_participant}"
                if mode == "livekit"
                else f"direct:{livekit_participant}:{scenario}:{run_nonce}"
            )

            direct_response, direct_latency, direct_err = await run_direct(
                example["prompt"],
                timeout_s=request_timeout_s,
                user_id=direct_user_id,
            )
            direct_quality_err = classify_response_failure(direct_response)
            direct_error = direct_err or direct_quality_err
            direct_pass = direct_error is None and bool(direct_response.strip())
            direct_runs.append(
                ExampleRun(
                    example_id=example["id"],
                    path="direct_backend",
                    prompt=example["prompt"],
                    response=direct_response,
                    latency_ms=direct_latency,
                    passed=direct_pass,
                    error=direct_error,
                    error_type=classify_runtime_error(direct_error, "direct_backend"),
                )
            )
            if not integration_boot_error and mode == "livekit" and active_scenario != scenario:
                if livekit_client is not None:
                    await livekit_client.close()
                scenario_room = livekit_room or (
                    f"phase4-gate-{scenario}-{int(time.time())}-{uuid.uuid4().hex[:6]}"
                )
                livekit_client = LiveKitFlutterClient(
                    token_server_url=token_server_url,
                    room_name=scenario_room,
                    participant_name=scenario_participant,
                    connect_timeout_s=livekit_connect_timeout_s,
                )
                try:
                    await livekit_client.connect()
                    probe_runtime_status = dict(
                        getattr(livekit_client, "last_probe_runtime_status", {}) or probe_runtime_status
                    )
                    active_scenario = scenario
                except Exception as e:
                    probe_runtime_status = dict(
                        getattr(livekit_client, "last_probe_runtime_status", {}) or probe_runtime_status
                    )
                    integration_boot_error = f"LiveKit scenario bootstrap failed: {e}"

            channels: List[str] = []
            if run_chat_suite:
                channels.append("chat")
            if run_voice_suite:
                channels.append("voice")

            for channel in channels:
                path_name = "flutter_chat" if channel == "chat" else "flutter_voice"
                run_bucket = flutter_chat_runs if channel == "chat" else flutter_voice_runs
                parity_bucket = chat_parity_results if channel == "chat" else voice_parity_results

                if integration_boot_error:
                    flutter_response, flutter_latency, flutter_err, simulated = (
                        "",
                        0.0,
                        integration_boot_error,
                        mode == "simulated",
                    )
                else:
                    flutter_response, flutter_latency, flutter_err, simulated = await run_flutter(
                        example["prompt"],
                        flutter_mode=mode,
                        flutter_api_url=flutter_api_url,
                        livekit_client=livekit_client,
                        desktop_client=desktop_client,
                        allow_simulated_flutter=allow_simulated_flutter,
                        channel=channel,
                        timeout_s=request_timeout_s,
                    )
                used_simulated_flutter = used_simulated_flutter or simulated
                flutter_quality_err = classify_response_failure(flutter_response)
                flutter_error = flutter_err or flutter_quality_err
                flutter_pass = flutter_error is None and bool(flutter_response.strip())
                run_bucket.append(
                    ExampleRun(
                        example_id=example["id"],
                        path=path_name,
                        prompt=example["prompt"],
                        response=flutter_response,
                        latency_ms=flutter_latency,
                        passed=flutter_pass,
                        error=flutter_error,
                        error_type=classify_runtime_error(flutter_error, path_name),
                        meta=(
                            dict(getattr(livekit_client, "last_observation", {}))
                            if mode == "livekit" and livekit_client is not None
                            else (
                                dict(getattr(desktop_client, "last_observation", {}))
                                if desktop_client is not None
                                else {}
                            )
                        ),
                    )
                )
                sem_ok = (
                    semantic_match(direct_response, flutter_response)
                    if (direct_pass and flutter_pass)
                    else False
                )
                fmt_ok = (
                    formatting_match(direct_response, flutter_response)
                    if (direct_pass and flutter_pass)
                    else False
                )
                latency_delta = max(0.0, flutter_latency - direct_latency)
                parity_bucket.append(
                    ExampleParity(
                        example_id=example["id"],
                        direct_passed=direct_pass,
                        flutter_passed=flutter_pass,
                        semantic_match=sem_ok,
                        formatting_match=fmt_ok,
                        latency_delta_ms=latency_delta,
                        passed=direct_pass and flutter_pass and sem_ok and fmt_ok,
                    )
                )

            if inter_example_delay_s > 0 and idx < (len(examples) - 1):
                await asyncio.sleep(inter_example_delay_s)
    finally:
        if livekit_client is not None:
            await livekit_client.close()
        if desktop_client is not None:
            await desktop_client.close()

    if run_tool_capability_matrix:
        if mode == "linux-desktop" and desktop_log_path and integration_boot_error:
            tool_capability_matrix = {
                "enabled": False,
                "mode": mode,
                "results": [],
                "summary": {},
                "error": f"Skipped due to integration bootstrap error: {integration_boot_error}",
            }
        else:
            # Reconnect desktop client after example suite if needed (it was closed in finally above).
            matrix_desktop_client: Optional[FlutterDesktopLogClient] = None
            matrix_livekit_client: Optional[LiveKitFlutterClient] = None
            try:
                if mode == "livekit":
                    matrix_livekit_client = LiveKitFlutterClient(
                        token_server_url=token_server_url,
                        room_name=livekit_room or f"phase4-gate-matrix-{int(time.time())}-{uuid.uuid4().hex[:6]}",
                        participant_name=build_scenario_participant(livekit_participant, f"tool-matrix-{run_nonce}"),
                        connect_timeout_s=livekit_connect_timeout_s,
                    )
                    await matrix_livekit_client.connect()
                if mode == "linux-desktop" and desktop_log_path:
                    matrix_desktop_client = FlutterDesktopLogClient(
                        log_path=str(desktop_log_path),
                        manual_mode=desktop_manual,
                        command_path=desktop_command_path,
                    )
                    await matrix_desktop_client.connect(timeout_s=livekit_connect_timeout_s)
                prompt_overrides = _load_prompt_overrides(desktop_prompt_file)
                tool_capability_matrix = await run_tool_capability_matrix_suite(
                    flutter_mode=mode,
                    flutter_api_url=flutter_api_url,
                    livekit_client=matrix_livekit_client,
                    desktop_client=matrix_desktop_client,
                    allow_simulated_flutter=allow_simulated_flutter,
                    prompt_overrides=prompt_overrides,
                    timeout_s=request_timeout_s,
                    inter_prompt_delay_s=max(inter_example_delay_s, 0.5),
                )
            except Exception as e:
                tool_capability_matrix = {
                    "enabled": False,
                    "mode": mode,
                    "results": [],
                    "summary": {},
                    "error": str(e),
                }
            finally:
                if matrix_livekit_client is not None:
                    await matrix_livekit_client.close()
                if matrix_desktop_client is not None:
                    await matrix_desktop_client.close()

    direct_latencies = [r.latency_ms for r in direct_runs if r.passed]
    flutter_chat_latencies = [r.latency_ms for r in flutter_chat_runs if r.passed]
    flutter_voice_latencies = [r.latency_ms for r in flutter_voice_runs if r.passed]
    direct_p95 = p95(direct_latencies)
    chat_p95 = p95(flutter_chat_latencies) if run_chat_suite else 0.0
    voice_p95 = p95(flutter_voice_latencies) if run_voice_suite else 0.0

    channel_threshold = (direct_p95 * 1.2) if direct_p95 > 0 else float("inf")
    chat_latency_threshold_ok = (chat_p95 <= channel_threshold) if run_chat_suite else True
    voice_latency_threshold_ok = (voice_p95 <= channel_threshold) if run_voice_suite else True
    latency_threshold_ok = chat_latency_threshold_ok and voice_latency_threshold_ok

    all_parity_entries: List[ExampleParity] = []
    if run_chat_suite:
        all_parity_entries.extend(chat_parity_results)
    if run_voice_suite:
        all_parity_entries.extend(voice_parity_results)

    def _example_passed_all_channels(example_id: str) -> bool:
        checks: List[bool] = []
        if run_chat_suite:
            p = next((item for item in chat_parity_results if item.example_id == example_id), None)
            checks.append(bool(p and p.passed))
        if run_voice_suite:
            p = next((item for item in voice_parity_results if item.example_id == example_id), None)
            checks.append(bool(p and p.passed))
        return all(checks) if checks else False

    feature_matrix = {name: False for name in FEATURE_CATEGORIES}
    for ex in examples:
        if ex["category"] in feature_matrix:
            feature_matrix[ex["category"]] = _example_passed_all_channels(ex["id"])
    memory_marker = any(
        any(marker in (r.response or "").lower() for marker in ("memory", "memories", "relevant past"))
        for r in direct_runs
    )
    feature_matrix["Memory interaction"] = feature_matrix.get("Memory interaction", False) or memory_marker
    feature_matrix["Cross-platform consistency"] = all(p.passed for p in all_parity_entries)

    max_levels = max(1, int(difficulty_levels))
    difficulty_tiers = {f"L{i}": False for i in range(1, max_levels + 1)}
    for ex in examples:
        tier = str(ex.get("difficulty") or "").upper()
        if tier in difficulty_tiers:
            difficulty_tiers[tier] = _example_passed_all_channels(str(ex.get("id")))

    errors: List[Dict[str, Any]] = []
    all_runs = direct_runs + flutter_chat_runs + flutter_voice_runs
    for run in all_runs:
        if run.error:
            errors.append(
                {
                    "type": run.error_type
                    or classify_runtime_error(run.error, run.path)
                    or ("integration_error" if run.path.startswith("flutter_") else "logic_error"),
                    "example_id": run.example_id,
                    "path": run.path,
                    "message": run.error,
                }
            )

    direct_by_id = {r.example_id: r for r in direct_runs}
    chat_by_id = {r.example_id: r for r in flutter_chat_runs}
    voice_by_id = {r.example_id: r for r in flutter_voice_runs}
    for channel_name, parity_bucket, channel_runs in (
        ("chat", chat_parity_results, chat_by_id),
        ("voice", voice_parity_results, voice_by_id),
    ):
        if channel_name == "chat" and not run_chat_suite:
            continue
        if channel_name == "voice" and not run_voice_suite:
            continue
        for parity in parity_bucket:
            if parity.passed:
                continue
            if any(
                err.get("example_id") == parity.example_id and err.get("path") == f"flutter_{channel_name}"
                for err in errors
            ):
                continue
            direct_run = direct_by_id.get(parity.example_id)
            flutter_run = channel_runs.get(parity.example_id)
            flutter_meta = flutter_run.meta if flutter_run else {}
            reasons: List[str] = []
            if not parity.direct_passed:
                reasons.append("direct path failed")
            if not parity.flutter_passed:
                reasons.append(f"{channel_name} path failed")
            if parity.direct_passed and parity.flutter_passed and not parity.semantic_match:
                reasons.append("semantic mismatch")
            if parity.direct_passed and parity.flutter_passed and not parity.formatting_match:
                reasons.append("format mismatch")
            if isinstance(flutter_meta, dict) and flutter_meta.get("matched_user_prompt") is False:
                reasons.append("manual prompt mismatch")
            message_parts = [", ".join(reasons) if reasons else "parity mismatch"]
            if direct_run and direct_run.response:
                message_parts.append(f"direct={summarize_text(direct_run.response)!r}")
            if flutter_run and flutter_run.response:
                message_parts.append(f"{channel_name}={summarize_text(flutter_run.response)!r}")
            errors.append(
                {
                    "type": "integration_error",
                    "example_id": parity.example_id,
                    "path": f"flutter_{channel_name}",
                    "message": "; ".join(message_parts),
                }
            )

    if used_simulated_flutter:
        errors.append(
            {
                "type": "integration_error",
                "example_id": "all",
                "path": "flutter_chat",
                "message": "Flutter validation used simulated backend path; use --flutter-mode livekit for real app flow.",
            }
        )

    all_structural_ok = all(c.passed for c in structural)
    all_features_ok = all(feature_matrix.values())
    all_difficulty_ok = all(difficulty_tiers.values())
    all_parity_ok = all(p.passed for p in all_parity_entries) and latency_threshold_ok
    no_open_errors = len(errors) == 0

    certified = all_structural_ok and all_features_ok and all_difficulty_ok and all_parity_ok and no_open_errors

    report = {
        "phase_audit_summary": {
            "structural_passed": all_structural_ok,
            "feature_matrix_passed": all_features_ok,
            "difficulty_passed": all_difficulty_ok,
            "parity_passed": all_parity_ok,
            "no_open_errors": no_open_errors,
        },
        "structural_checks": [asdict(c) for c in structural],
        "test_matrix": feature_matrix,
        "difficulty_tier_results": difficulty_tiers,
        "integration_validation_results": {
            "flutter_mode": mode,
            "transport_kind": (
                "flutter_desktop_app"
                if mode == "linux-desktop"
                else ("flutter_transport_probe" if mode == "livekit" else mode)
            ),
            "direct_p95_ms": direct_p95,
            "flutter_chat_p95_ms": chat_p95,
            "flutter_voice_p95_ms": voice_p95,
            "latency_threshold_ok": latency_threshold_ok,
            "chat_latency_threshold_ok": chat_latency_threshold_ok,
            "voice_latency_threshold_ok": voice_latency_threshold_ok,
            "chat_parity_results": [asdict(p) for p in chat_parity_results],
            "voice_parity_results": [asdict(p) for p in voice_parity_results],
            "parity_results": [asdict(p) for p in all_parity_entries],
            "run_chat_suite": run_chat_suite,
            "run_voice_suite": run_voice_suite,
            "used_simulated_flutter": used_simulated_flutter,
            "livekit_room": livekit_client.room_name if livekit_client else None,
            "desktop_log_path": str(desktop_log_path) if desktop_log_path else None,
            "desktop_command_path": str(desktop_command_path) if desktop_command_path else None,
            "probe_runtime_status": probe_runtime_status,
            "provider_profile": provider_profile_info,
        },
        "example_runs": {
            "direct": [asdict(r) for r in direct_runs],
            "flutter_chat": [asdict(r) for r in flutter_chat_runs],
            "flutter_voice": [asdict(r) for r in flutter_voice_runs],
        },
        "error_report": errors,
        "tool_capability_matrix": tool_capability_matrix,
    }

    if certified:
        report["certification_status"] = {
            "phase_status": "CERTIFIED",
            "regressions": 0,
            "integration_status": "STABLE",
            "ready_for_next_phase": True,
        }
    else:
        report["certification_status"] = {
            "phase_status": "FAILED",
            "ready_for_next_phase": False,
        }

    return report


def render_report(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Phase Audit Summary")
    summary = report["phase_audit_summary"]
    for k, v in summary.items():
        lines.append(f"- {k}: {v}")

    lines.append("\n# Test Matrix Table")
    for k, v in report["test_matrix"].items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")

    lines.append("\n# Difficulty Tier Results")
    for k, v in report["difficulty_tier_results"].items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")

    lines.append("\n# Integration Validation Results")
    integration = report["integration_validation_results"]
    lines.append(f"- flutter_mode: {integration.get('flutter_mode')}")
    lines.append(f"- transport_kind: {integration.get('transport_kind')}")
    lines.append(f"- livekit_room: {integration.get('livekit_room')}")
    lines.append(f"- desktop_log_path: {integration.get('desktop_log_path')}")
    lines.append(f"- desktop_command_path: {integration.get('desktop_command_path')}")
    lines.append(f"- direct_p95_ms: {integration['direct_p95_ms']:.2f}")
    lines.append(f"- flutter_chat_p95_ms: {integration.get('flutter_chat_p95_ms', 0.0):.2f}")
    lines.append(f"- flutter_voice_p95_ms: {integration.get('flutter_voice_p95_ms', 0.0):.2f}")
    lines.append(f"- latency_threshold_ok: {integration['latency_threshold_ok']}")
    lines.append(f"- chat_latency_threshold_ok: {integration.get('chat_latency_threshold_ok')}")
    lines.append(f"- voice_latency_threshold_ok: {integration.get('voice_latency_threshold_ok')}")
    lines.append(f"- run_chat_suite: {integration.get('run_chat_suite')}")
    lines.append(f"- run_voice_suite: {integration.get('run_voice_suite')}")
    lines.append(f"- used_simulated_flutter: {integration['used_simulated_flutter']}")
    probe_status = integration.get("probe_runtime_status") or {}
    if probe_status:
        lines.append(f"- probe_runtime_status: {probe_status.get('status')}")
        if probe_status.get("diagnostic_report"):
            lines.append(f"- probe_runtime_diagnostic_report: {probe_status.get('diagnostic_report')}")
    provider_profile = integration.get("provider_profile") or {}
    if provider_profile:
        lines.append(
            f"- provider_profile: {provider_profile.get('provider_profile')} "
            f"-> {provider_profile.get('resolved_provider')} ({provider_profile.get('resolved_model')})"
        )

    lines.append("\n# Tool Capability Matrix")
    tool_matrix = report.get("tool_capability_matrix") or {}
    if not tool_matrix:
        lines.append("- None")
    elif not tool_matrix.get("enabled"):
        lines.append(f"- enabled: False")
        if tool_matrix.get("error"):
            lines.append(f"- error: {tool_matrix.get('error')}")
    else:
        summary_tm = tool_matrix.get("summary", {})
        lines.append(f"- enabled: True")
        lines.append(f"- variants_total: {summary_tm.get('variants_total')}")
        lines.append(f"- variant_pass_rate: {summary_tm.get('variant_pass_rate')}")
        lines.append(f"- family_pass_rate: {summary_tm.get('family_pass_rate')}")
        lines.append(f"- unique_tool_names_invoked: {summary_tm.get('unique_tool_names_invoked')}")
        lines.append(f"- tool_selection_consistency: {summary_tm.get('tool_selection_consistency')}")
        lines.append(
            f"- planner_vs_direct_tool_routing_accuracy: "
            f"{summary_tm.get('planner_vs_direct_tool_routing_accuracy')}"
        )

    lines.append("\n# Error Report")
    if report["error_report"]:
        for err in report["error_report"]:
            lines.append(f"- [{err['type']}] {err['example_id']} ({err['path']}): {err['message']}")
    else:
        lines.append("- None")

    lines.append("\n# Certification Status")
    lines.append(json.dumps(report["certification_status"], indent=2))

    lines.append("\n# Next Phase Decision")
    next_phase = "Proceed to Phase 5" if report["certification_status"].get("ready_for_next_phase") else "Blocked"
    lines.append(f"- {next_phase}")

    return "\n".join(lines)


async def _main_async(args: argparse.Namespace) -> int:
    report = await run_gatekeeper(
        flutter_mode=args.flutter_mode,
        flutter_api_url=args.flutter_api_url,
        token_server_url=args.token_server_url,
        livekit_room=args.livekit_room,
        livekit_participant=args.livekit_participant,
        livekit_connect_timeout_s=args.livekit_connect_timeout_s,
        desktop_log_path=args.desktop_log_path,
        desktop_manual=args.desktop_manual,
        desktop_prompt_file=args.desktop_prompt_file,
        desktop_command_path=args.desktop_command_path,
        allow_simulated_flutter=args.allow_simulated_flutter,
        provider_profile=args.provider_profile,
        run_tool_capability_matrix=args.run_tool_capability_matrix,
        suite_file=args.suite_file,
        difficulty_levels=args.difficulty_levels,
        run_voice_suite=args.run_voice_suite,
        run_chat_suite=args.run_chat_suite,
        request_timeout_s=args.request_timeout_s,
        inter_example_delay_s=args.inter_example_delay_s,
    )

    output_text = render_report(report)
    print(output_text)

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote JSON report to: {out_path}")

    if args.output_text:
        out_path = Path(args.output_text)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"Wrote text report to: {out_path}")

    return 0 if report["certification_status"].get("phase_status") == "CERTIFIED" else 1


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase Gatekeeper validation runner")
    parser.add_argument(
        "--flutter-mode",
        type=str,
        default="livekit",
        choices=["livekit", "linux-desktop", "http", "simulated"],
        help="Flutter-triggered path mode: livekit probe, linux-desktop app evidence, http adapter, or simulated.",
    )
    parser.add_argument(
        "--flutter-api-url",
        type=str,
        default=None,
        help="HTTP endpoint for flutter_mode=http (POST JSON {message}).",
    )
    parser.add_argument(
        "--token-server-url",
        type=str,
        default="http://127.0.0.1:5050",
        help="Token server base URL for flutter_mode=livekit.",
    )
    parser.add_argument(
        "--livekit-room",
        type=str,
        default=None,
        help="Optional fixed LiveKit room name for flutter_mode=livekit.",
    )
    parser.add_argument(
        "--livekit-participant",
        type=str,
        default="phase-gatekeeper-probe",
        help="Probe participant identity for flutter_mode=livekit.",
    )
    parser.add_argument(
        "--livekit-connect-timeout-s",
        type=float,
        default=45.0,
        help="Timeout waiting for agent participant join in flutter_mode=livekit.",
    )
    parser.add_argument(
        "--allow-simulated-flutter",
        action="store_true",
        help="Permit flutter_mode=simulated fallback through orchestrator path.",
    )
    parser.add_argument(
        "--desktop-log-path",
        type=str,
        default="/tmp/maya_flutter_gatekeeper.jsonl",
        help="Flutter Linux desktop gatekeeper JSONL evidence log path.",
    )
    parser.add_argument(
        "--desktop-manual",
        action="store_true",
        help="Manual operator mode for flutter_mode=linux-desktop (enter prompts in app UI).",
    )
    parser.add_argument(
        "--desktop-prompt-file",
        type=str,
        default=None,
        help="Optional JSON or newline prompt file for linux-desktop capability matrix prompt overrides.",
    )
    parser.add_argument(
        "--desktop-command-path",
        type=str,
        default=None,
        help="Optional command pipe JSONL path for linux-desktop autopilot prompt dispatch.",
    )
    parser.add_argument(
        "--provider-profile",
        type=str,
        default="auto",
        choices=["auto", "deepseek", "groq", "nvidia", "perplexity"],
        help="Provider profile for direct/simulated validation runs. 'auto' prefers Nvidia/DeepSeek if keys exist.",
    )
    parser.add_argument(
        "--run-tool-capability-matrix",
        action="store_true",
        help="Run the 24-prompt tool capability variation matrix (best used with flutter_mode=linux-desktop).",
    )
    parser.add_argument(
        "--suite-file",
        type=str,
        default=str(AGENT_ROOT / "scripts" / "gatekeeper_suites" / "phase5_7x14.json"),
        help="Path to gatekeeper suite JSON with examples.",
    )
    parser.add_argument(
        "--difficulty-levels",
        type=int,
        default=7,
        help="Number of difficulty levels that must pass.",
    )
    parser.add_argument(
        "--run-voice-suite",
        action="store_true",
        help="Run voice-path examples in addition to chat path.",
    )
    parser.add_argument(
        "--no-run-voice-suite",
        action="store_false",
        dest="run_voice_suite",
        help="Disable voice-path examples.",
    )
    parser.add_argument(
        "--run-chat-suite",
        action="store_true",
        help="Run chat-path examples.",
    )
    parser.add_argument(
        "--no-run-chat-suite",
        action="store_false",
        dest="run_chat_suite",
        help="Disable chat-path examples.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=str(AGENT_ROOT / "reports" / "phase4_gatekeeper_report.json"),
        help="Path to write JSON report.",
    )
    parser.add_argument(
        "--output-text",
        type=str,
        default=str(AGENT_ROOT / "reports" / "phase4_gatekeeper_report.md"),
        help="Path to write markdown-like text report.",
    )
    parser.add_argument(
        "--request-timeout-s",
        type=float,
        default=12.0,
        help="Per-example timeout budget (seconds) for each path.",
    )
    parser.add_argument(
        "--inter-example-delay-s",
        type=float,
        default=1.5,
        help="Delay between examples to reduce provider burst-rate failures.",
    )
    parser.set_defaults(run_voice_suite=True, run_chat_suite=True)
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
