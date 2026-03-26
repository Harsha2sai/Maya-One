import json

from core.orchestrator import AgentOrchestrator


class DummyParticipant:
    def __init__(self, metadata):
        self.metadata = metadata


class DummyParticipantWithNoMetadata(DummyParticipant):
    def __init__(self):
        super().__init__(metadata=None)


class DummyParticipantInvalid(DummyParticipant):
    def __init__(self):
        super().__init__(metadata="{invalid-json)")


def test_parse_client_config_returns_dict_on_valid_metadata():
    payload = {"llm_provider": "openai", "room": "test-room"}
    participant = DummyParticipant(metadata=json.dumps(payload))

    parsed = AgentOrchestrator.parse_client_config(participant)

    assert parsed == payload


def test_parse_client_config_handles_missing_metadata():
    participant = DummyParticipantWithNoMetadata()

    parsed = AgentOrchestrator.parse_client_config(participant)

    assert parsed == {}


def test_parse_client_config_handles_invalid_json(caplog):
    participant = DummyParticipantInvalid()

    parsed = AgentOrchestrator.parse_client_config(participant)

    assert parsed == {}
    assert "Failed to parse" in caplog.text
