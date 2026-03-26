#!/usr/bin/env python3
"""
Full voice roundtrip verification:
user audio -> STT -> LLM -> TTS (via LiveKit room).

This script:
1. Starts `agent.py dev`
2. Waits for token server readiness on :5050
3. Creates a LiveKit room and dispatches the configured agent name
4. Connects a probe participant
5. Publishes a microphone track with synthesized speech audio
6. Verifies the agent responds after the injected utterance

Exit codes:
  0 = PASS
  2 = roundtrip failed
  3 = startup/health failure
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib import request

import edge_tts
from dotenv import load_dotenv
from livekit import rtc
from livekit.api import LiveKitAPI, CreateRoomRequest, CreateAgentDispatchRequest
from livekit.agents.utils import codecs


QUESTION = "Please answer in one short sentence. What is two plus two?"
VOICE = "en-US-JennyNeural"
SAMPLE_RATE = 24000
NUM_CHANNELS = 1
FRAME_MS = 20


def post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def synth_to_pcm(text: str, voice: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice=voice)
    decoder = codecs.AudioStreamDecoder(
        sample_rate=SAMPLE_RATE,
        num_channels=NUM_CHANNELS,
        format="audio/mpeg",
    )
    pcm = bytearray()

    async def _decode_task():
        async for frame in decoder:
            pcm.extend(frame.data.tobytes())

    task = asyncio.create_task(_decode_task())
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            decoder.push(chunk["data"])
    decoder.end_input()
    await task
    return bytes(pcm)


async def publish_pcm_audio(source: rtc.AudioSource, pcm: bytes) -> None:
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


def wait_health(url: str, timeout_s: int = 60) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(1)
    return False


async def run_probe(agent_name: str) -> bool:    # Connect to room to listen for agent
    room_name = f"maya-voice-rt-{int(time.time())}"

    # logger.info("Connecting to Room as tester...") # logger is not defined, omitting this line
    active_slot = os.getenv("LIVEKIT_ACTIVE_SLOT", "1").strip()
    suffix = "_2" if active_slot == "2" else ""
    
    lk = LiveKitAPI(
        url=os.getenv(f"LIVEKIT_URL{suffix}"),
        api_key=os.getenv(f"LIVEKIT_API_KEY{suffix}"),
        api_secret=os.getenv(f"LIVEKIT_API_SECRET{suffix}"),
    )

    room = rtc.Room()
    source: rtc.AudioSource | None = None

    events = {
        "participant_connected": 0,
        "track_subscribed": 0,
        "transcription_received": 0,
        "data_received": 0,
    }
    transcripts: list[tuple[float, str, str]] = []

    @room.on("participant_connected")
    def _on_participant_connected(p):
        events["participant_connected"] += 1
        print("event participant_connected", getattr(p, "identity", None))

    @room.on("track_subscribed")
    def _on_track_subscribed(track, publication, participant):
        events["track_subscribed"] += 1
        print("event track_subscribed", getattr(track, "kind", None), getattr(participant, "identity", None))

    @room.on("transcription_received")
    def _on_transcription_received(segments, participant, publication):
        events["transcription_received"] += 1
        text = " ".join(getattr(s, "text", "") for s in segments).strip()
        who = getattr(participant, "identity", "unknown")
        transcripts.append((time.time(), who, text))
        print("event transcription", who, text)

    @room.on("data_received")
    def _on_data_received(packet):
        events["data_received"] += 1

    try:
        try:
            await lk.room.create_room(CreateRoomRequest(name=room_name))
        except Exception:
            # Room may already exist in rare retries.
            pass

        dispatch = await lk.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata='{"probe":"voice_roundtrip"}',
            )
        )
        print("dispatch_id", dispatch.id)

        token_resp = post_json(
            "http://127.0.0.1:5050/token",
            {
                "roomName": room_name,
                "participantName": "voice-probe-user",
                "metadata": {"probe": "voice_roundtrip"},
            },
        )

        await room.connect(token_resp["url"], token_resp["token"])

        for _ in range(40):
            if len(room.remote_participants) > 0:
                break
            await asyncio.sleep(1)

        remote_count = len(room.remote_participants)
        print("remote_participants", remote_count)

        # Publish microphone track and inject speech audio.
        source = rtc.AudioSource(sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS)
        local_track = rtc.LocalAudioTrack.create_audio_track("voice_probe_mic", source)
        opts = rtc.TrackPublishOptions()
        opts.source = rtc.TrackSource.SOURCE_MICROPHONE
        pub = await room.local_participant.publish_track(local_track, opts)
        print("published_track_sid", getattr(pub, "sid", None))

        await asyncio.sleep(8)
        baseline = len(transcripts)

        pcm = await synth_to_pcm(QUESTION, VOICE)
        injection_start = time.time()
        print("injected_pcm_bytes", len(pcm))
        await publish_pcm_audio(source, pcm)
        print("audio_injected")

        await asyncio.sleep(18)

        post = [t for t in transcripts[baseline:] if t[0] >= injection_start and t[2]]
        post_texts = [t[2] for t in post]
        print("events_summary", events)
        print("post_transcriptions_count", len(post_texts))

        for txt in post_texts:
            print("post_transcription_text", txt)

        has_agent_join = remote_count == 1
        has_audio = events["track_subscribed"] > 0
        has_post_speech = len(post_texts) > 0

        greeting_phrases = {"hello", "hello, i am maya.", "hello i am maya"}
        normalized = [" ".join(t.lower().split()) for t in post_texts]
        meaningful = [t for t in normalized if t not in greeting_phrases]
        has_meaningful_response = len(meaningful) > 0

        print("check_single_agent_join", has_agent_join)
        print("check_audio_track", has_audio)
        print("check_post_speech", has_post_speech)
        print("check_meaningful_response", has_meaningful_response)

        passed = has_agent_join and has_audio and has_post_speech and has_meaningful_response
        print("ROUNDTRIP_RESULT", "PASS" if passed else "FAIL")
        return passed
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


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    load_dotenv(".env")

    agent_name = os.getenv("LIVEKIT_AGENT_NAME", "maya-one")
    print(f"Using LIVEKIT_AGENT_NAME={agent_name}")

    cleanup_script = root / "scripts" / "cleanup_ports.sh"
    if cleanup_script.exists():
        subprocess.run(["bash", str(cleanup_script)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    log_path = Path("/tmp/maya_voice_roundtrip_worker.log")
    with log_path.open("w") as logf:
        proc = subprocess.Popen(
            [str(root / "venv" / "bin" / "python"), "agent.py", "dev"],
            cwd=str(root),
            stdout=logf,
            stderr=subprocess.STDOUT,
            text=True,
        )

    try:
        if not wait_health("http://127.0.0.1:5050/health", timeout_s=70):
            print("FAIL: token server not ready on :5050")
            return 3

        passed = asyncio.run(run_probe(agent_name))
        return 0 if passed else 2
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
