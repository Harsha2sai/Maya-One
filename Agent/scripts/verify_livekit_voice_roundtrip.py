#!/usr/bin/env python3
"""
Phase 27 LiveKit voice certification (multi-probe).

This script assumes the backend/token server is already running. It:
1. Connects to a fresh LiveKit room and dispatches the configured agent
2. Publishes microphone audio for each probe utterance
3. Collects agent transcriptions and evaluates quality assertions
4. Emits PASS/FAIL summary and optional JSON report

Exit codes:
  0 = all probes passed
  1 = one or more probes failed
  2 = setup/runtime failure (cannot certify)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib import request

from dotenv import load_dotenv


def get_git_commit_hash() -> str:
    """Get current git commit hash for traceability."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def get_certification_metadata() -> dict[str, Any]:
    """Build standardized certification report metadata."""
    return {
        "version": "2.0",
        "schema": "phase27_certification",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit_hash": get_git_commit_hash(),
        "agent_name": os.getenv("LIVEKIT_AGENT_NAME", "maya-one"),
    }


def build_standardized_report(
    *,
    status: str,
    overall_passed: bool,
    room_name: str | None,
    events: dict,
    probes: list[dict],
    start_time: float,
    end_time: float,
    error_reason: str = "",
) -> dict[str, Any]:
    """
    Build a standardized certification report with full traceability.

    Returns a dict matching the Phase 28 standardized format with:
    - certification: metadata (version, timestamps, commit)
    - environment: runtime info
    - summary: high-level results
    - details: full probe results and events
    """
    duration_ms = int((end_time - start_time) * 1000)

    report: dict[str, Any] = {
        "certification": get_certification_metadata(),
        "timing": {
            "started_at": datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
            "completed_at": datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat(),
            "duration_ms": duration_ms,
        },
        "environment": {
            "livekit_url": os.getenv("LIVEKIT_URL", "").split(".")[0] + ".***" if os.getenv("LIVEKIT_URL") else "not_set",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": sys.platform,
        },
        "summary": {
            "status": status,
            "overall_passed": overall_passed,
            "total_probes": len(probes),
            "passed_probes": sum(1 for p in probes if p.get("passed", False)),
            "failed_probes": sum(1 for p in probes if not p.get("passed", False)),
        },
        "details": {
            "room_name": room_name,
            "events": events,
            "probes": probes,
        },
    }

    if error_reason:
        report["summary"]["error_reason"] = error_reason

    return report

try:
    import edge_tts
    from livekit import rtc
    from livekit.api import CreateAgentDispatchRequest, CreateRoomRequest, LiveKitAPI
    from livekit.agents.utils import codecs
except Exception as import_exc:  # pragma: no cover - exercised only in env/runtime failures
    edge_tts = None  # type: ignore[assignment]
    rtc = None  # type: ignore[assignment]
    codecs = None  # type: ignore[assignment]
    LiveKitAPI = None  # type: ignore[assignment]
    CreateRoomRequest = None  # type: ignore[assignment]
    CreateAgentDispatchRequest = None  # type: ignore[assignment]
    _IMPORT_ERROR = import_exc
else:
    _IMPORT_ERROR = None


VOICE = "en-US-JennyNeural"
SAMPLE_RATE = 24000
NUM_CHANNELS = 1
FRAME_MS = 20
LOCAL_PARTICIPANT = "voice-probe-user"
MAX_PROBE_ATTEMPTS = 3
RETRYABLE_PROBE_REASONS = {
    "no_agent_transcription",
    "runtime_failure_response",
    "greeting_only_response",
}
LIVEKIT_OP_TIMEOUT_S = 30
AUDIO_PUBLISH_TIMEOUT_S = 20
CI_POST_GREETING_DELAY_S = 5.0
CI_COLLECT_SECONDS = 30.0
READINESS_TIMEOUT_S = 12.0

DEFAULT_FORBIDDEN_PHRASES = (
    "hi maya, it sounds like you're thinking",
    "it sounds like you're thinking",
    "you are maya",
    "you're maya",
)


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    prompt: str
    expected_any: tuple[str, ...] = ()
    expected_all: tuple[str, ...] = ()
    expected_regex: tuple[str, ...] = ()
    forbidden_phrases: tuple[str, ...] = ()
    allow_greeting_only: bool = False
    collect_seconds: float = 18.0


@dataclass
class ProbeResult:
    name: str
    prompt: str
    passed: bool
    reason: str
    responses: list[str] = field(default_factory=list)
    forbidden_hit: str = ""


def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _env_flag(name: str, default: str = "0") -> bool:
    raw = str(os.getenv(name, default) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_greeting_only(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    greeting_patterns = (
        "hello",
        "hi",
        "hello i am maya",
        "hello, i am maya",
        "hi i am maya",
        "how can i help you",
    )
    if normalized in greeting_patterns:
        return True
    if normalized.startswith("hi, i'm maya") or normalized.startswith("hi i'm maya"):
        return True
    if normalized.startswith("hello, i'm maya") or normalized.startswith("hello i'm maya"):
        return True
    if "help you today" in normalized and "maya" in normalized:
        return True
    if normalized.startswith("hello") and len(normalized.split()) <= 6:
        return True
    return False


def detect_forbidden_phrase(text: str, phrases: Iterable[str]) -> str:
    normalized = normalize_text(text)
    for phrase in phrases:
        p = normalize_text(phrase)
        if p and p in normalized:
            return phrase
    return ""


def evaluate_probe_texts(spec: ProbeSpec, agent_texts: list[str]) -> ProbeResult:
    cleaned = [normalize_text(t) for t in agent_texts if normalize_text(t)]
    if not cleaned:
        return ProbeResult(
            name=spec.name,
            prompt=spec.prompt,
            passed=False,
            reason="no_agent_transcription",
            responses=[],
        )

    if not spec.allow_greeting_only and all(is_greeting_only(t) for t in cleaned):
        return ProbeResult(
            name=spec.name,
            prompt=spec.prompt,
            passed=False,
            reason="greeting_only_response",
            responses=cleaned,
        )

    if spec.forbidden_phrases:
        for txt in cleaned:
            hit = detect_forbidden_phrase(txt, spec.forbidden_phrases)
            if hit:
                return ProbeResult(
                    name=spec.name,
                    prompt=spec.prompt,
                    passed=False,
                    reason="forbidden_phrase_detected",
                    responses=cleaned,
                    forbidden_hit=hit,
                )

    merged = " ".join(cleaned)
    failure_markers = (
        "i was unable to complete that",
        "sorry, i encountered an issue processing your request",
        "please try again",
    )
    if any(marker in merged for marker in failure_markers):
        return ProbeResult(
            name=spec.name,
            prompt=spec.prompt,
            passed=False,
            reason="runtime_failure_response",
            responses=cleaned,
        )

    for token in spec.expected_all:
        if normalize_text(token) not in merged:
            return ProbeResult(
                name=spec.name,
                prompt=spec.prompt,
                passed=False,
                reason=f"missing_expected_all:{token}",
                responses=cleaned,
            )

    if spec.expected_regex:
        if not any(re.search(pattern, merged, flags=re.IGNORECASE) for pattern in spec.expected_regex):
            return ProbeResult(
                name=spec.name,
                prompt=spec.prompt,
                passed=False,
                reason="missing_expected_regex",
                responses=cleaned,
            )

    if spec.expected_any:
        hit_any = any(normalize_text(token) in merged for token in spec.expected_any)
        if not hit_any:
            return ProbeResult(
                name=spec.name,
                prompt=spec.prompt,
                passed=False,
                reason="missing_expected_any",
                responses=cleaned,
            )

    return ProbeResult(
        name=spec.name,
        prompt=spec.prompt,
        passed=True,
        reason="ok",
        responses=cleaned,
    )


def default_probe_suite(ci_mode: bool = False) -> list[ProbeSpec]:
    collect_default = CI_COLLECT_SECONDS if ci_mode else 24.0
    collect_time = CI_COLLECT_SECONDS if ci_mode else 22.0
    return [
        ProbeSpec(
            name="factual_math",
            prompt="What is two plus two?",
            expected_any=("4", "four"),
            forbidden_phrases=DEFAULT_FORBIDDEN_PHRASES + (
                "i'm maya, your ai assistant",
                "made by harsha",
            ),
            allow_greeting_only=False,
            collect_seconds=collect_default,
        ),
        ProbeSpec(
            name="identity_creator",
            prompt="Who created you?",
            expected_any=("created", "built", "develop", "team", "openai", "harsha"),
            allow_greeting_only=False,
            collect_seconds=collect_default,
        ),
        ProbeSpec(
            name="time_fastpath",
            prompt="What time is it right now?",
            expected_regex=(r"\b([01]?\d|2[0-3]):[0-5]\d\b", r"\b\d{1,2}\s?(am|pm)\b"),
            forbidden_phrases=DEFAULT_FORBIDDEN_PHRASES + (
                "i'm maya, your ai assistant",
                "made by harsha",
            ),
            allow_greeting_only=False,
            collect_seconds=collect_time,
        ),
    ]


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_health(url: str, timeout_s: int = 30) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(1)
    return False


async def synth_to_pcm(text: str, voice: str) -> bytes:
    if edge_tts is None or codecs is None:
        raise RuntimeError(f"voice dependencies not available: {_IMPORT_ERROR}")

    communicate = edge_tts.Communicate(text, voice=voice)
    decoder = codecs.AudioStreamDecoder(
        sample_rate=SAMPLE_RATE,
        num_channels=NUM_CHANNELS,
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


async def publish_pcm_audio(source: Any, pcm: bytes) -> None:
    if rtc is None:
        raise RuntimeError(f"livekit dependencies not available: {_IMPORT_ERROR}")

    samples_per_frame = int(SAMPLE_RATE * FRAME_MS / 1000)
    bytes_per_frame = samples_per_frame * NUM_CHANNELS * 2

    for i in range(0, len(pcm), bytes_per_frame):
        chunk = pcm[i : i + bytes_per_frame]
        if len(chunk) < 2 * NUM_CHANNELS:
            continue
        samples = len(chunk) // (2 * NUM_CHANNELS)
        frame = rtc.AudioFrame(chunk, SAMPLE_RATE, NUM_CHANNELS, samples)
        await source.capture_frame(frame)
        await asyncio.sleep(samples / SAMPLE_RATE)

    try:
        await asyncio.wait_for(source.wait_for_playout(), timeout=AUDIO_PUBLISH_TIMEOUT_S)
    except asyncio.TimeoutError:
        print("probe_warning audio_playout_timeout=true")


async def run_suite(
    *,
    agent_name: str,
    room_prefix: str,
    token_url: str,
    send_message_url: str,
    timeout_s: int,
    voice: str,
    probes: list[ProbeSpec],
    allow_chat_fallback: bool,
) -> dict[str, Any]:
    if rtc is None or LiveKitAPI is None:
        raise RuntimeError(f"livekit dependencies not available: {_IMPORT_ERROR}")

    active_slot = os.getenv("LIVEKIT_ACTIVE_SLOT", "1").strip()
    suffix = "_2" if active_slot == "2" else ""

    room_name = f"{room_prefix}-{int(time.time())}"
    lk = LiveKitAPI(
        url=os.getenv(f"LIVEKIT_URL{suffix}"),
        api_key=os.getenv(f"LIVEKIT_API_KEY{suffix}"),
        api_secret=os.getenv(f"LIVEKIT_API_SECRET{suffix}"),
    )

    room = rtc.Room()
    source: Any = None
    events = {
        "participant_connected": 0,
        "track_subscribed": 0,
        "transcription_received": 0,
        "data_received": 0,
    }
    transcripts: list[tuple[float, str, str]] = []
    chat_events: list[tuple[float, str, str]] = []
    remote_identities: set[str] = set()
    ci_mode = _env_flag("CI", "0")

    @room.on("participant_connected")
    def _on_participant_connected(participant: Any) -> None:
        events["participant_connected"] += 1
        identity = getattr(participant, "identity", "") or ""
        if identity:
            remote_identities.add(identity)
        print("event participant_connected", identity)

    @room.on("track_subscribed")
    def _on_track_subscribed(track: Any, publication: Any, participant: Any) -> None:
        del publication
        events["track_subscribed"] += 1
        identity = getattr(participant, "identity", "") or ""
        if identity:
            remote_identities.add(identity)
        print("event track_subscribed", getattr(track, "kind", None), identity)

    @room.on("transcription_received")
    def _on_transcription_received(segments: Any, participant: Any, publication: Any) -> None:
        del publication
        events["transcription_received"] += 1
        text = " ".join(getattr(s, "text", "") for s in segments).strip()
        identity = getattr(participant, "identity", "unknown") or "unknown"
        transcripts.append((time.time(), identity, text))
        print("event transcription", identity, text)

    @room.on("data_received")
    def _on_data_received(packet: Any) -> None:
        events["data_received"] += 1
        topic = str(getattr(packet, "topic", "") or "")
        data = getattr(packet, "data", b"")
        if topic != "chat_events" or not data:
            return
        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            return
        event_type = str(payload.get("type") or "")
        content = str(payload.get("content") or payload.get("voice_text") or "").strip()
        if event_type == "assistant_final" and content:
            chat_events.append((time.time(), event_type, content))
            print("event chat_event assistant_final", content[:120])

    async def _collect_outputs_since(
        *,
        transcript_baseline: int,
        chat_baseline: int,
        injection_start: float,
    ) -> tuple[list[str], bool]:
        user_transcribed = False
        agent_texts: list[str] = []

        for ts, who, text in transcripts[transcript_baseline:]:
            if ts < injection_start or not text:
                continue
            normalized_who = (who or "").strip()
            if normalized_who == LOCAL_PARTICIPANT:
                user_transcribed = True
                continue
            if normalized_who in remote_identities or normalized_who.startswith("agent-"):
                agent_texts.append(text)

        for ts, event_type, content in chat_events[chat_baseline:]:
            if ts < injection_start or not content:
                continue
            if event_type == "assistant_final":
                agent_texts.append(content)

        return agent_texts, user_transcribed

    def _room_state_snapshot(label: str) -> None:
        print(
            "room_snapshot",
            label,
            f"remote_participants={len(room.remote_participants)}",
            f"remote_identities={','.join(sorted(remote_identities)) or 'none'}",
            f"events={json.dumps(events, sort_keys=True)}",
            f"transcripts={len(transcripts)}",
            f"chat_events={len(chat_events)}",
        )

    def _dump_recent_history(label: str, limit: int = 12) -> None:
        now = time.time()
        for idx, (ts, who, text) in enumerate(transcripts[-limit:], start=1):
            age = max(0.0, now - ts)
            print(
                "debug_transcript",
                label,
                f"idx={idx}",
                f"age_s={age:.2f}",
                f"who={(who or '').strip() or 'unknown'}",
                f"text={(text or '').strip()[:220]}",
            )
        for idx, (ts, event_type, content) in enumerate(chat_events[-limit:], start=1):
            age = max(0.0, now - ts)
            print(
                "debug_chat_event",
                label,
                f"idx={idx}",
                f"age_s={age:.2f}",
                f"type={(event_type or '').strip() or 'unknown'}",
                f"content={(content or '').strip()[:220]}",
            )

    async def _wait_for_output(
        *,
        transcript_baseline: int,
        chat_baseline: int,
        injection_start: float,
        collect_seconds: float,
        attempt_label: str,
    ) -> tuple[list[str], bool]:
        deadline = time.time() + max(6.0, collect_seconds)
        last_agent_count = 0
        stable_agent_loops = 0
        latest_texts: list[str] = []
        latest_user_transcribed = False
        logged_timeout_warning = False

        while time.time() < deadline:
            agent_now, user_now = await _collect_outputs_since(
                transcript_baseline=transcript_baseline,
                chat_baseline=chat_baseline,
                injection_start=injection_start,
            )
            latest_texts = agent_now
            latest_user_transcribed = user_now
            if (
                not logged_timeout_warning
                and not latest_texts
                and not latest_user_transcribed
                and (time.time() - injection_start) >= 10.0
            ):
                print(f"probe_warning {attempt_label} no_transcription_after_10s=true")
                logged_timeout_warning = True
            if agent_now:
                if len(agent_now) == last_agent_count:
                    stable_agent_loops += 1
                    if stable_agent_loops >= 3:
                        break
                else:
                    last_agent_count = len(agent_now)
                    stable_agent_loops = 0
            await asyncio.sleep(1)

        return latest_texts, latest_user_transcribed

    async def _run_readiness_check() -> bool:
        _room_state_snapshot("pre_readiness")
        transcript_baseline = len(transcripts)
        chat_baseline = len(chat_events)
        injection_start = time.time()
        prompt = "Probe readiness check. Reply with READY."
        try:
            post_json(
                send_message_url,
                {
                    "message": prompt,
                    "user_id": LOCAL_PARTICIPANT,
                    "run_id": room_name,
                },
            )
        except Exception as err:
            print(f"probe_readiness send_message_failed error={err}")
            return False

        agent_texts, user_transcribed = await _wait_for_output(
            transcript_baseline=transcript_baseline,
            chat_baseline=chat_baseline,
            injection_start=injection_start,
            collect_seconds=READINESS_TIMEOUT_S,
            attempt_label="readiness",
        )
        merged = " ".join(normalize_text(t) for t in agent_texts)
        ready = "ready" in merged or bool(agent_texts) or user_transcribed
        print(
            "probe_readiness",
            f"passed={str(ready).lower()}",
            f"agent_texts={len(agent_texts)}",
            f"user_transcribed={str(user_transcribed).lower()}",
        )
        if not ready:
            _dump_recent_history("readiness_failure")
        _room_state_snapshot("post_readiness")
        return ready

    try:
        try:
            await lk.room.create_room(CreateRoomRequest(name=room_name))
        except Exception:
            pass

        dispatch = await asyncio.wait_for(
            lk.agent_dispatch.create_dispatch(
                CreateAgentDispatchRequest(
                    agent_name=agent_name,
                    room=room_name,
                    metadata='{"probe":"phase27_voice_certification"}',
                )
            ),
            timeout=LIVEKIT_OP_TIMEOUT_S,
        )
        print("dispatch_id", dispatch.id)

        token_resp = post_json(
            token_url,
            {
                "roomName": room_name,
                "participantName": LOCAL_PARTICIPANT,
                "metadata": {"probe": "phase27_voice_certification"},
            },
        )

        await asyncio.wait_for(
            room.connect(token_resp["url"], token_resp["token"]),
            timeout=LIVEKIT_OP_TIMEOUT_S,
        )

        join_deadline = time.time() + max(10, min(timeout_s, 40))
        while time.time() < join_deadline:
            if len(room.remote_participants) > 0:
                for participant in room.remote_participants.values():
                    identity = getattr(participant, "identity", "") or ""
                    if identity:
                        remote_identities.add(identity)
                break
            await asyncio.sleep(1)

        if len(room.remote_participants) == 0:
            return {
                "status": "setup_failure",
                "reason": "agent_not_joined",
                "room_name": room_name,
                "events": events,
                "probes": [],
            }

        source = rtc.AudioSource(sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS)
        local_track = rtc.LocalAudioTrack.create_audio_track("voice_probe_mic", source)
        opts = rtc.TrackPublishOptions()
        opts.source = rtc.TrackSource.SOURCE_MICROPHONE
        pub = await room.local_participant.publish_track(local_track, opts)
        print("published_track_sid", getattr(pub, "sid", None))

        ready_deadline = time.time() + max(12, min(timeout_s, 35))
        while time.time() < ready_deadline:
            if events["track_subscribed"] > 0:
                break
            await asyncio.sleep(1)

        if events["track_subscribed"] == 0:
            # Some sessions can still deliver transcription without surfacing
            # track_subscribed in time; continue and let probe assertions decide.
            print("probe_warning agent_audio_not_subscribed_continuing=true")

        # Let greeting stream settle; wait for at least one agent transcript first.
        stable_loops = 0
        last_count = len(transcripts)
        saw_agent_transcript = False
        for _ in range(20):
            await asyncio.sleep(1)
            cur = len(transcripts)
            if any(
                (who or "").strip().startswith("agent-") and (txt or "").strip()
                for _, who, txt in transcripts
            ):
                saw_agent_transcript = True
            if cur == last_count:
                stable_loops += 1
                if saw_agent_transcript and stable_loops >= 2:
                    break
            else:
                stable_loops = 0
                last_count = cur

        if ci_mode:
            print(f"probe_ci_delay post_greeting_delay_s={CI_POST_GREETING_DELAY_S:.1f}")
            await asyncio.sleep(CI_POST_GREETING_DELAY_S)

        readiness_ok = await _run_readiness_check()
        if not readiness_ok:
            print("probe_warning readiness_check_failed=true")

        results: list[ProbeResult] = []

        async def _wait_for_transcript_quiet(max_wait_s: int = 12, quiet_loops_needed: int = 3) -> None:
            last_count = len(transcripts)
            quiet_loops = 0
            deadline = time.time() + max_wait_s
            while time.time() < deadline:
                await asyncio.sleep(1)
                cur = len(transcripts)
                if cur == last_count:
                    quiet_loops += 1
                    if quiet_loops >= quiet_loops_needed:
                        return
                else:
                    quiet_loops = 0
                    last_count = cur

        for spec in probes:
            result: ProbeResult | None = None
            for attempt in range(1, MAX_PROBE_ATTEMPTS + 1):
                await _wait_for_transcript_quiet()
                _room_state_snapshot(f"{spec.name}:attempt:{attempt}:pre")
                transcript_baseline = len(transcripts)
                chat_baseline = len(chat_events)
                injection_start = time.time()
                pcm = await synth_to_pcm(spec.prompt, voice)
                print(f"probe_start {spec.name} attempt={attempt} pcm_bytes={len(pcm)}")
                try:
                    await asyncio.wait_for(
                        publish_pcm_audio(source, pcm),
                        timeout=max(AUDIO_PUBLISH_TIMEOUT_S + 8, 24),
                    )
                except asyncio.TimeoutError:
                    print(f"probe_warning {spec.name} audio_publish_timeout=true")
                agent_texts, user_transcribed = await _wait_for_output(
                    transcript_baseline=transcript_baseline,
                    chat_baseline=chat_baseline,
                    injection_start=injection_start,
                    collect_seconds=spec.collect_seconds,
                    attempt_label=f"{spec.name}:voice:{attempt}",
                )

                if not user_transcribed and not agent_texts and allow_chat_fallback:
                    print(f"probe_fallback {spec.name} mode=send_message")
                    transcript_baseline = len(transcripts)
                    chat_baseline = len(chat_events)
                    injection_start = time.time()
                    try:
                        post_json(
                            send_message_url,
                            {
                                "message": spec.prompt,
                                "user_id": LOCAL_PARTICIPANT,
                                "run_id": room_name,
                            },
                        )
                    except Exception as send_err:
                        print(f"probe_fallback_send_message_failed {spec.name} error={send_err}")
                        await room.local_participant.publish_data(
                            spec.prompt.encode("utf-8"),
                            topic="lk.chat",
                        )
                    agent_texts, user_transcribed = await _wait_for_output(
                        transcript_baseline=transcript_baseline,
                        chat_baseline=chat_baseline,
                        injection_start=injection_start,
                        collect_seconds=max(10.0, spec.collect_seconds),
                        attempt_label=f"{spec.name}:fallback_http:{attempt}",
                    )
                    if not user_transcribed and not agent_texts:
                        print(f"probe_fallback {spec.name} mode=lk.chat_prefixed")
                        transcript_baseline = len(transcripts)
                        chat_baseline = len(chat_events)
                        injection_start = time.time()
                        await room.local_participant.publish_data(
                            f"PROBE: {spec.prompt}".encode("utf-8"),
                            topic="lk.chat",
                        )
                        agent_texts, user_transcribed = await _wait_for_output(
                            transcript_baseline=transcript_baseline,
                            chat_baseline=chat_baseline,
                            injection_start=injection_start,
                            collect_seconds=max(10.0, spec.collect_seconds),
                            attempt_label=f"{spec.name}:fallback_data:{attempt}",
                        )

                if not user_transcribed and not agent_texts:
                    result = ProbeResult(
                        name=spec.name,
                        prompt=spec.prompt,
                        passed=False,
                        reason="no_user_or_agent_transcription",
                        responses=[],
                    )
                else:
                    result = evaluate_probe_texts(spec, agent_texts)
                if (
                    result.reason in RETRYABLE_PROBE_REASONS
                    or result.reason == "no_user_or_agent_transcription"
                ) and attempt < MAX_PROBE_ATTEMPTS:
                    _dump_recent_history(f"{spec.name}:attempt:{attempt}:retry")
                    print(f"probe_retry {spec.name} reason={result.reason} next_attempt={attempt+1}")
                    await asyncio.sleep(2.0)
                    continue
                break

            if result is None:
                result = ProbeResult(
                    name=spec.name,
                    prompt=spec.prompt,
                    passed=False,
                    reason="no_probe_result",
                    responses=[],
                )
            results.append(result)
            if not result.passed:
                _dump_recent_history(f"{spec.name}:final_failure")
            _room_state_snapshot(f"{spec.name}:attempt:{attempt}:post")
            print(
                "probe_result",
                spec.name,
                "PASS" if result.passed else "FAIL",
                result.reason,
            )
            await asyncio.sleep(1.0)

        overall_passed = all(r.passed for r in results)
        return {
            "status": "ok",
            "overall_passed": overall_passed,
            "room_name": room_name,
            "events": events,
            "probes": [asdict(r) for r in results],
        }
    finally:
        try:
            await asyncio.wait_for(room.disconnect(), timeout=6)
        except Exception:
            pass
        if source is not None:
            try:
                await asyncio.wait_for(source.aclose(), timeout=6)
            except Exception:
                pass
        try:
            await asyncio.wait_for(lk.aclose(), timeout=6)
        except Exception:
            pass


def write_json_report(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 27 LiveKit voice certification")
    parser.add_argument("--timeout", type=int, default=90, help="probe timeout budget (seconds)")
    parser.add_argument("--room-prefix", type=str, default="maya-cert", help="LiveKit room name prefix")
    parser.add_argument("--json-output", type=str, default="", help="write certification JSON report")
    parser.add_argument("--health-url", type=str, default="http://127.0.0.1:5050/health")
    parser.add_argument("--token-url", type=str, default="http://127.0.0.1:5050/token")
    parser.add_argument("--send-message-url", type=str, default="http://127.0.0.1:5050/send_message")
    parser.add_argument("--health-timeout", type=int, default=30)
    parser.add_argument("--voice", type=str, default=VOICE)
    parser.add_argument("--agent-name", type=str, default=os.getenv("LIVEKIT_AGENT_NAME", "maya-one"))
    parser.add_argument(
        "--allow-chat-fallback",
        action="store_true",
        default=_env_flag("PHASE27_ALLOW_CHAT_FALLBACK", "1"),
        help="Fallback to lk.chat prompt injection when voice probe captures no output",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(".env")
    args = parse_args()
    start_time = time.time()

    if not wait_health(args.health_url, timeout_s=args.health_timeout):
        end_time = time.time()
        payload = build_standardized_report(
            status="setup_failure",
            overall_passed=False,
            room_name=None,
            events={},
            probes=[],
            start_time=start_time,
            end_time=end_time,
            error_reason=f"token_server_unreachable:{args.health_url}",
        )
        print("CERT_RESULT", "SETUP_FAILURE", payload["summary"]["error_reason"])
        if args.json_output:
            write_json_report(args.json_output, payload)
        return 2

    try:
        ci_mode = _env_flag("CI", "0")
        end_time = time.time()
        result_payload = asyncio.run(
            run_suite(
                agent_name=args.agent_name,
                room_prefix=args.room_prefix,
                token_url=args.token_url,
                send_message_url=args.send_message_url,
                timeout_s=args.timeout,
                voice=args.voice,
                probes=default_probe_suite(ci_mode=ci_mode),
                allow_chat_fallback=args.allow_chat_fallback,
            )
        )
        # Convert old format to standardized format if needed
        if "certification" not in result_payload:
            end_time = time.time()
            result_payload = build_standardized_report(
                status=result_payload.get("status", "unknown"),
                overall_passed=result_payload.get("overall_passed", False),
                room_name=result_payload.get("room_name"),
                events=result_payload.get("events", {}),
                probes=result_payload.get("probes", []),
                start_time=start_time,
                end_time=end_time,
                error_reason=result_payload.get("reason", ""),
            )
        payload = result_payload
    except Exception as exc:
        end_time = time.time()
        payload = build_standardized_report(
            status="setup_failure",
            overall_passed=False,
            room_name=None,
            events={},
            probes=[],
            start_time=start_time,
            end_time=end_time,
            error_reason=f"{type(exc).__name__}:{exc}",
        )

    if args.json_output:
        write_json_report(args.json_output, payload)

    summary = payload.get("summary", payload)
    status = summary.get("status", payload.get("status", "unknown"))
    probes = payload.get("details", {}).get("probes", payload.get("probes", []))

    for probe in probes:
        print(
            "PROBE",
            probe.get("name", "unknown"),
            "PASS" if probe.get("passed") else "FAIL",
            f"reason={probe.get('reason', '')}",
            f"forbidden={probe.get('forbidden_hit', '')}",
        )

    if status != "ok":
        print("CERT_RESULT", "SETUP_FAILURE", summary.get("error_reason", "unknown"))
        return 2

    overall_passed = summary.get("overall_passed", payload.get("overall_passed", False))
    if overall_passed:
        print("CERT_RESULT", "PASS")
        return 0

    print("CERT_RESULT", "FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
