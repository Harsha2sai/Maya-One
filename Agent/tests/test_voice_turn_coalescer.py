import agent


def test_voice_final_segments_are_coalesced_into_single_dispatch():
    coalescer = agent.VoiceTurnCoalescer(window_s=0.85)

    first = coalescer.add_segment(
        sender="livekit:user-1",
        text="Who is the prime minister of India",
        participant=None,
        source_event_id="seg-1",
        ingress_received_mono=10.0,
        now=100.0,
    )
    second = coalescer.add_segment(
        sender="livekit:user-1",
        text="and what he does?",
        participant=None,
        source_event_id="seg-2",
        ingress_received_mono=10.1,
        now=100.4,
    )

    assert first["segments"] == 1
    assert second["segments"] == 2
    assert second["merged"] is True
    assert second["text"] == "Who is the prime minister of India and what he does?"


def test_voice_final_segments_reset_after_window():
    coalescer = agent.VoiceTurnCoalescer(window_s=0.85)

    coalescer.add_segment(
        sender="livekit:user-1",
        text="Who is the CEO of OpenAI",
        participant=None,
        source_event_id="seg-1",
        ingress_received_mono=11.0,
        now=200.0,
    )
    later = coalescer.add_segment(
        sender="livekit:user-1",
        text="tell me more",
        participant=None,
        source_event_id="seg-2",
        ingress_received_mono=12.0,
        now=201.0,
    )

    assert later["segments"] == 1
    assert later["merged"] is False
    assert later["text"] == "tell me more"
