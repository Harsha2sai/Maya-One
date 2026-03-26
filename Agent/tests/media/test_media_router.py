from core.media.media_router import MediaRouter


def test_media_router_parses_next_command() -> None:
    router = MediaRouter()
    cmd = router.parse("skip this song")
    assert cmd.action == "next"


def test_media_router_prefers_youtube_for_video_query() -> None:
    router = MediaRouter()
    cmd = router.parse("play lo-fi video on youtube")
    provider = router.choose_provider(cmd)
    assert provider == "youtube"


def test_media_router_extracts_play_query() -> None:
    router = MediaRouter()
    cmd = router.parse("play blinding lights on spotify")
    assert cmd.action == "play"
    assert "blinding lights" in cmd.query


def test_media_router_maps_start_playing_to_play_action() -> None:
    router = MediaRouter()
    cmd = router.parse("start playing music")
    assert cmd.action == "play"


def test_media_router_maps_put_on_phrase_to_play_action() -> None:
    router = MediaRouter()
    cmd = router.parse("put on some jazz")
    assert cmd.action == "play"
