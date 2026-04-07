"""Unit tests for Phase 27 voice certification verdict logic."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "verify_livekit_voice_roundtrip.py"
    spec = importlib.util.spec_from_file_location("voice_probe", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_is_greeting_only_detection():
    mod = _load_module()
    assert mod.is_greeting_only("Hello, I am Maya") is True
    assert mod.is_greeting_only("Hello") is True
    assert mod.is_greeting_only("The answer is four") is False


def test_evaluate_probe_fails_on_greeting_only_response():
    mod = _load_module()
    spec = mod.ProbeSpec(name="factual", prompt="q", expected_any=("4",))
    result = mod.evaluate_probe_texts(spec, ["Hello, I am Maya"])
    assert result.passed is False
    assert result.reason == "greeting_only_response"


def test_evaluate_probe_detects_forbidden_phrase():
    mod = _load_module()
    spec = mod.ProbeSpec(
        name="factual",
        prompt="q",
        expected_any=("4",),
        forbidden_phrases=("it sounds like you're thinking",),
    )
    result = mod.evaluate_probe_texts(
        spec,
        ["Hi Maya, it sounds like you're thinking of a question with answer four"],
    )
    assert result.passed is False
    assert result.reason == "forbidden_phrase_detected"
    assert result.forbidden_hit == "it sounds like you're thinking"


def test_evaluate_probe_requires_expected_any_token():
    mod = _load_module()
    spec = mod.ProbeSpec(name="factual", prompt="q", expected_any=("4", "four"))
    result = mod.evaluate_probe_texts(spec, ["The answer is five"])
    assert result.passed is False
    assert result.reason == "missing_expected_any"


def test_evaluate_probe_passes_with_expected_any_token():
    mod = _load_module()
    spec = mod.ProbeSpec(name="factual", prompt="q", expected_any=("4", "four"))
    result = mod.evaluate_probe_texts(spec, ["The answer is four."])
    assert result.passed is True
    assert result.reason == "ok"


def test_default_probe_suite_contract():
    mod = _load_module()
    names = {probe.name for probe in mod.default_probe_suite()}
    assert names == {"factual_math", "identity_creator", "time_fastpath"}


def test_time_probe_requires_time_regex_not_identity_text():
    mod = _load_module()
    spec = mod.ProbeSpec(name="time", prompt="q", expected_regex=(r"\b([01]?\d|2[0-3]):[0-5]\d\b",))
    result = mod.evaluate_probe_texts(spec, ["I'm Maya, your AI assistant, made by Harsha."])
    assert result.passed is False
    assert result.reason == "missing_expected_regex"


def test_evaluate_probe_detects_text_chat_gate_response():
    mod = _load_module()
    spec = mod.ProbeSpec(name="factual", prompt="q", expected_any=("4",))
    result = mod.evaluate_probe_texts(
        spec,
        ["Text chat is available from architecture Phase 2+. Please use voice in the current mode."],
    )
    assert result.passed is False
    assert result.reason == "text_chat_gate_active"
