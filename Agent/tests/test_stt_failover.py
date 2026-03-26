import socket

import pytest

from providers import sttprovider


def test_build_stt_with_failover_on_deepgram_probe_failure(monkeypatch):
    def _fake_probe(timeout_s: float = 2.0):
        return False, "dns_fail"

    def _fake_get_stt_provider(provider_name: str, language: str = "en", model: str = "", **kwargs):
        return {"provider": provider_name, "language": language, "model": model}

    monkeypatch.setattr(sttprovider, "probe_deepgram_connectivity", _fake_probe)
    monkeypatch.setattr(sttprovider, "get_stt_provider", _fake_get_stt_provider)

    provider, active, degraded, reason = sttprovider.build_stt_with_failover(
        provider_name="deepgram",
        language="en-US",
        model="nova-2",
        failover_enabled=True,
        failover_target="groq",
        probe_timeout_s=1.0,
    )

    assert provider["provider"] == "groq"
    assert active == "groq"
    assert degraded is True
    assert reason and reason.startswith("deepgram_probe_failed:")


def test_is_deepgram_connection_error():
    assert sttprovider.is_deepgram_connection_error("failed to connect to deepgram")
    assert sttprovider.is_deepgram_connection_error("ClientConnectorDNSError for api.deepgram.com")
    assert not sttprovider.is_deepgram_connection_error("some unrelated exception")


def test_probe_deepgram_connectivity_handles_socket_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise socket.gaierror("mock dns error")

    monkeypatch.setattr(socket, "getaddrinfo", _raise)
    ok, reason = sttprovider.probe_deepgram_connectivity(timeout_s=0.2)
    assert ok is False
    assert "gaierror" in reason.lower() or "mock dns error" in reason.lower()


def test_build_stt_with_failover_uses_azure_secondary_when_groq_fails(monkeypatch):
    monkeypatch.setenv("STT_SECONDARY_FALLBACK", "azure")

    def _fake_probe(timeout_s: float = 2.0):
        return True, "ok"

    calls = []

    def _fake_get_stt_provider(provider_name: str, language: str = "en", model: str = "", **kwargs):
        calls.append(provider_name)
        if provider_name == "deepgram":
            raise RuntimeError("deepgram init failed")
        if provider_name == "groq":
            raise RuntimeError("groq init failed")
        return {"provider": provider_name, "language": language, "model": model}

    monkeypatch.setattr(sttprovider, "probe_deepgram_connectivity", _fake_probe)
    monkeypatch.setattr(sttprovider, "get_stt_provider", _fake_get_stt_provider)

    provider, active, degraded, reason = sttprovider.build_stt_with_failover(
        provider_name="deepgram",
        language="en-US",
        model="nova-2",
        failover_enabled=True,
        failover_target="groq",
        probe_timeout_s=1.0,
    )

    assert calls == ["deepgram", "groq", "azure"]
    assert provider["provider"] == "azure"
    assert active == "azure"
    assert degraded is True
    assert reason and reason.startswith("stt_init_failed:")
