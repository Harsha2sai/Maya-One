from types import SimpleNamespace

import pytest

from livekit.agents.inference import llm as inference_llm
from livekit.agents.llm import utils as llm_utils

import utils.schema_fixer as schema_fixer


@pytest.fixture
def reset_schema_fixer_state():
    original_stream_init = inference_llm.LLMStream.__init__
    try:
        yield
    finally:
        inference_llm.LLMStream.__init__ = original_stream_init
        schema_fixer._patched = False


def _fake_build_legacy(function_tool, *, internally_tagged=False):
    if internally_tagged:
        return {"parameters": {"type": "object", "required": []}}
    return {"function": {"parameters": {"type": "object", "required": []}}}


def _fake_build_strict(function_tool):
    return {"function": {"parameters": {"type": "object", "required": []}}}


def _tool_stub():
    return SimpleNamespace(info=SimpleNamespace(name="noop"))


def test_apply_schema_patch_preserves_strict_schema_for_openai(monkeypatch, reset_schema_fixer_state):
    monkeypatch.setattr(llm_utils, "build_legacy_openai_schema", _fake_build_legacy)
    monkeypatch.setattr(llm_utils, "build_strict_openai_schema", _fake_build_strict)

    schema_fixer.apply_schema_patch("openai")

    assert not getattr(inference_llm.LLMStream.__init__, "_is_patched_init", False)

    tool = _tool_stub()
    legacy = llm_utils.build_legacy_openai_schema(tool)
    strict = llm_utils.build_strict_openai_schema(tool)
    tagged = llm_utils.build_legacy_openai_schema(tool, internally_tagged=True)

    assert legacy["function"]["parameters"]["properties"] == {}
    assert strict["function"]["parameters"]["properties"] == {}
    assert tagged["parameters"]["properties"] == {}


def test_apply_schema_patch_forces_loose_schema_for_groq(monkeypatch, reset_schema_fixer_state):
    monkeypatch.setattr(llm_utils, "build_legacy_openai_schema", _fake_build_legacy)
    monkeypatch.setattr(llm_utils, "build_strict_openai_schema", _fake_build_strict)

    schema_fixer.apply_schema_patch("groq")

    assert getattr(inference_llm.LLMStream.__init__, "_is_patched_init", False)

    tool = _tool_stub()
    legacy = llm_utils.build_legacy_openai_schema(tool)
    strict = llm_utils.build_strict_openai_schema(tool)

    assert legacy["function"]["parameters"]["properties"] == {}
    assert strict["function"]["parameters"]["properties"] == {}
