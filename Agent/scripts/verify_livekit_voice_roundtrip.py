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
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib import request

from dotenv import load_dotenv

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


def default_probe_suite() -> list[ProbeSpec]:
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
            collect_seconds=24.0,
        ),
        ProbeSpec(
            name="identity_creator",
            prompt="Who created you?",
            expected_any=("created", "built", "develop", "team", "openai", "harsha"),
            allow_greeting_only=False,
            collect_seconds=24.0,
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
            collect_seconds=22.0,
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

    await source.wait_for_playout()


async def run_suite(
    *,
    agent_name: str,
    room_prefix: str,
    token_url: str,
    timeout_s: int,
    voice: str,
    probes: list[ProbeSpec],
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
    remote_identities: set[str] = set()

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
        del packet
        events["data_received"] += 1

    try:
        try:
            await lk.room.create_room(CreateRoomRequest(name=room_name))
        except Exception:
            pass

        dispatch = await lk.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata='{"probe":"phase27_voice_certification"}',
            )
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

        await room.connect(token_resp["url"], token_resp["token"])

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
            return {
                "status": "setup_failure",
                "reason": "agent_audio_not_subscribed",
                "room_name": room_name,
                "events": events,
                "probes": [],
            }

        # Let greeting stream settle; otherwise first probe STT can truncate.
        stable_loops = 0
        last_count = len(transcripts)
        for _ in range(12):
            await asyncio.sleep(1)
            cur = len(transcripts)
            if cur == last_count:
                stable_loops += 1
                if stable_loops >= 2:
                    break
            else:
                stable_loops = 0
                last_count = cur

        results: list[ProbeResult] = []
        for spec in probes:
            baseline = len(transcripts)
            injection_start = time.time()
            pcm = await synth_to_pcm(spec.prompt, voice)
            print(f"probe_start {spec.name} pcm_bytes={len(pcm)}")
            await publish_pcm_audio(source, pcm)

            # Wait up to collect_seconds; if a response appears, stop after brief stabilization.
            deadline = time.time() + max(6.0, spec.collect_seconds)
            last_agent_count = 0
            stable_agent_loops = 0
            while time.time() < deadline:
                post_now = transcripts[baseline:]
                agent_now = []
                for ts, who, text in post_now:
                    if ts < injection_start or not text:
                        continue
                    normalized_who = (who or "").strip()
                    if normalized_who == LOCAL_PARTICIPANT:
                        continue
                    if normalized_who in remote_identities or normalized_who.startswith("agent-"):
                        agent_now.append(text)
                if agent_now:
                    if len(agent_now) == last_agent_count:
                        stable_agent_loops += 1
                        if stable_agent_loops >= 3:
                            break
                    else:
                        last_agent_count = len(agent_now)
                        stable_agent_loops = 0
                await asyncio.sleep(1)

            post = transcripts[baseline:]
            agent_texts = []
            for ts, who, text in post:
                if ts < injection_start or not text:
                    continue
                normalized_who = (who or "").strip()
                if normalized_who == LOCAL_PARTICIPANT:
                    continue
                if normalized_who in remote_identities or normalized_who.startswith("agent-"):
                    agent_texts.append(text)

            result = evaluate_probe_texts(spec, agent_texts)
            results.append(result)
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
            await room.disconnect()
        except Exception:
            pass
        if source is not None:
            try:
                await source.aclose()
            except Exception:
                pass
        await lk.aclose()


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
    parser.add_argument("--health-timeout", type=int, default=30)
    parser.add_argument("--voice", type=str, default=VOICE)
    parser.add_argument("--agent-name", type=str, default=os.getenv("LIVEKIT_AGENT_NAME", "maya-one"))
    return parser.parse_args()


def main() -> int:
    load_dotenv(".env")
    args = parse_args()

    if not wait_health(args.health_url, timeout_s=args.health_timeout):
        payload = {
            "status": "setup_failure",
            "reason": f"token_server_unreachable:{args.health_url}",
            "overall_passed": False,
            "probes": [],
        }
        print("CERT_RESULT", "SETUP_FAILURE", payload["reason"])
        if args.json_output:
            write_json_report(args.json_output, payload)
        return 2

    try:
        payload = asyncio.run(
            run_suite(
                agent_name=args.agent_name,
                room_prefix=args.room_prefix,
                token_url=args.token_url,
                timeout_s=args.timeout,
                voice=args.voice,
                probes=default_probe_suite(),
            )
        )
    except Exception as exc:
        payload = {
            "status": "setup_failure",
            "reason": f"runtime_error:{type(exc).__name__}:{exc}",
            "overall_passed": False,
            "probes": [],
        }

    if args.json_output:
        write_json_report(args.json_output, payload)

    status = payload.get("status")
    for probe in payload.get("probes", []):
        print(
            "PROBE",
            probe.get("name"),
            "PASS" if probe.get("passed") else "FAIL",
            f"reason={probe.get('reason', '')}",
            f"forbidden={probe.get('forbidden_hit', '')}",
        )

    if status != "ok":
        print("CERT_RESULT", "SETUP_FAILURE", payload.get("reason", "unknown"))
        return 2

    if payload.get("overall_passed"):
        print("CERT_RESULT", "PASS")
        return 0

    print("CERT_RESULT", "FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
