from core.media.media_models import MediaResult, MediaTrack


def test_media_result_event_payload_contains_track_fields() -> None:
    result = MediaResult(
        success=True,
        action="play",
        provider="spotify",
        message="Now playing",
        track=MediaTrack(title="Song", artist="Artist", url="https://open.spotify.com/track/1"),
    )

    payload = result.to_event_payload()
    assert payload["action"] == "play"
    assert payload["provider"] == "spotify"
    assert payload["track_name"] == "Song"
    assert payload["artist"] == "Artist"


def test_media_track_domain_extracts_hostname() -> None:
    track = MediaTrack(title="Song", url="https://www.youtube.com/watch?v=abc")
    assert track.domain == "youtube.com"
