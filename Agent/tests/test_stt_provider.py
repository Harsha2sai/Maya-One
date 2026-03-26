from providers import sttprovider
import agent


def test_deepgram_config_uses_env_vars(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_LANGUAGE", "en-IN")
    monkeypatch.setenv("DEEPGRAM_MODEL", "nova-2-general")
    monkeypatch.setenv("DEEPGRAM_ENDPOINTING_MS", "700")

    language, model, options = sttprovider._resolve_deepgram_runtime_config(  # pylint: disable=protected-access
        language="en-US",
        model="nova-2",
        kwargs={},
        supported_params={"endpointing_ms"},
    )

    assert language == "en-IN"
    assert model == "nova-2-general"
    assert options["endpointing_ms"] == 700
    assert options["interim_results"] is False
    assert options["smart_format"] is True


def test_stt_endpointing_config_uses_env_vars(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_ENDPOINTING_MS", "850")
    _language, _model, options = sttprovider._resolve_deepgram_runtime_config(  # pylint: disable=protected-access
        language="en-US",
        model="nova-2",
        kwargs={},
        supported_params={"endpointing_ms"},
    )
    assert options["endpointing_ms"] == 850

    monkeypatch.setenv("MIN_ENDPOINTING_DELAY", "1.7")
    monkeypatch.setenv("MAX_ENDPOINTING_DELAY", "3.6")
    monkeypatch.setenv("VOICE_MIN_ENDPOINTING_DELAY_S", "1.1")
    monkeypatch.setenv("VOICE_MAX_ENDPOINTING_DELAY_S", "2.0")
    min_delay, max_delay = agent._resolve_endpointing_delays()
    assert min_delay == 1.7
    assert max_delay == 3.6


def test_transcript_validation_rejects_fragments():
    assert not sttprovider.is_valid_voice_transcript("AI.")
    assert not sttprovider.is_valid_voice_transcript("")
    assert not sttprovider.is_valid_voice_transcript("   ")


def test_transcript_validation_rejects_inaudible_marker():
    assert not sttprovider.is_valid_voice_transcript("[INAUDIBLE]")


def test_transcript_validation_rejects_repeated_char_hallucination():
    assert not sttprovider.is_valid_voice_transcript("aaaaaaaaaa")


def test_transcript_validation_rejects_repetitive_filler_chain():
    assert not sttprovider.is_valid_voice_transcript("um um um um")


def test_transcript_validation_accepts_good_input():
    assert sttprovider.is_valid_voice_transcript("What is the weather in Hyderabad?")
    assert sttprovider.is_valid_voice_transcript("Open downloads folder")
    assert sttprovider.is_valid_voice_transcript("Set a reminder for 8pm")
