import json

import pytest

from api.handlers import _provider_id_to_env_var, handle_get_api_status


def test_connector_toggle_key_mapping():
    assert _provider_id_to_env_var("connector_spotify_enabled") == "CONNECTOR_SPOTIFY_ENABLED"
    assert _provider_id_to_env_var("connector_github_enabled") == "CONNECTOR_GITHUB_ENABLED"


@pytest.mark.asyncio
async def test_api_status_includes_connector_capabilities(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONNECTOR_SPOTIFY_ENABLED", "true")
    monkeypatch.setenv("CONNECTOR_YOUTUBE_ENABLED", "false")
    monkeypatch.delenv("CONNECTOR_SLACK_ENABLED", raising=False)

    response = await handle_get_api_status(None)
    assert response.status == 200

    payload = json.loads(response.text)
    connectors = payload["connectors"]

    assert payload["status"]["connector_spotify_enabled"] is True
    assert payload["status"]["connector_youtube_enabled"] is False

    assert connectors["spotify"]["enabled"] is True
    assert connectors["spotify"]["available"] is True
    assert connectors["spotify"]["reason"] == ""

    assert connectors["youtube"]["enabled"] is False
    assert connectors["youtube"]["available"] is True

    assert connectors["slack"]["available"] is False
    assert connectors["slack"]["reason"] != ""
