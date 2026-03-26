from unittest.mock import MagicMock, patch

from providers.factory import ProviderFactory


def setup_function() -> None:
    ProviderFactory.reset_cache()


def test_edge_requested_prefers_cartesia_primary():
    edge_instance = MagicMock(name="edge_tts")

    with patch("providers.factory.get_tts_provider", return_value=edge_instance) as mock_get_tts:
        resolved = ProviderFactory.get_tts("edge_tts", "en-US-JennyNeural", "")

    assert resolved is edge_instance
    assert mock_get_tts.call_args_list[0].kwargs["provider_name"] == "edge_tts"


def test_edge_requested_uses_elevenlabs_when_cartesia_fails():
    eleven_instance = MagicMock(name="elevenlabs_tts")

    with patch("providers.factory.get_tts_provider") as mock_get_tts:
        mock_get_tts.side_effect = [ValueError("edge missing"), ValueError("cartesia missing"), eleven_instance]
        resolved = ProviderFactory.get_tts("edge_tts", "en-US-JennyNeural", "")

    assert resolved is eleven_instance
    providers = [call.kwargs["provider_name"] for call in mock_get_tts.call_args_list]
    assert providers[:3] == ["edge_tts", "elevenlabs", "cartesia"]


def test_edge_requested_uses_edge_as_fallback_only():
    edge_instance = MagicMock(name="edge_tts")

    with patch("providers.factory.get_tts_provider") as mock_get_tts:
        mock_get_tts.side_effect = [
            edge_instance,
        ]
        resolved = ProviderFactory.get_tts("edge_tts", "en-US-JennyNeural", "")

    assert resolved is edge_instance
    providers = [call.kwargs["provider_name"] for call in mock_get_tts.call_args_list]
    assert providers == ["edge_tts"]


def test_edge_requested_can_prefer_premium_when_enabled(monkeypatch):
    monkeypatch.setenv("TTS_EDGE_PREFERS_PREMIUM", "true")
    elevenlabs_instance = MagicMock(name="elevenlabs_tts")

    with patch("providers.factory.get_tts_provider", return_value=elevenlabs_instance) as mock_get_tts:
        resolved = ProviderFactory.get_tts("edge_tts", "en-US-JennyNeural", "")

    assert resolved is elevenlabs_instance
    assert mock_get_tts.call_args_list[0].kwargs["provider_name"] == "elevenlabs"


def test_edge_requested_drops_uuid_like_voice_to_default():
    edge_instance = MagicMock(name="edge_tts")

    with patch("providers.factory.get_tts_provider", return_value=edge_instance) as mock_get_tts:
        resolved = ProviderFactory.get_tts("edge_tts", "21m00Tcm4TlvDq8ikWAM", "eleven_turbo_v2")

    assert resolved is edge_instance
    kwargs = mock_get_tts.call_args_list[0].kwargs
    assert kwargs["provider_name"] == "edge_tts"
    assert kwargs["voice"] == ""
    assert kwargs["model"] == ""
