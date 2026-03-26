from pathlib import Path

import pytest

from scripts.phase_gatekeeper_validation import load_example_suite, run_flutter


def test_gatekeeper_suite_loader_7x14():
    suite_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "gatekeeper_suites"
        / "phase5_7x14.json"
    )
    examples = load_example_suite(str(suite_path))
    assert len(examples) == 14
    levels = {ex["difficulty"] for ex in examples}
    assert levels.issuperset({"L1", "L2", "L3", "L4", "L5", "L6", "L7"})


@pytest.mark.asyncio
async def test_run_flutter_livekit_voice_channel_uses_voice_send():
    class _FakeLiveKitClient:
        async def send_and_wait(self, prompt: str, timeout_s: float = 25.0):
            return f"chat:{prompt}", 10.0, None

        async def send_voice_and_wait(self, prompt: str, timeout_s: float = 25.0):
            return f"voice:{prompt}", 20.0, None

    response, latency_ms, error, simulated = await run_flutter(
        "hello",
        flutter_mode="livekit",
        flutter_api_url=None,
        livekit_client=_FakeLiveKitClient(),
        desktop_client=None,
        allow_simulated_flutter=False,
        channel="voice",
        timeout_s=5.0,
    )

    assert error is None
    assert simulated is False
    assert response == "voice:hello"
    assert latency_ms == 20.0
