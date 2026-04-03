from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import json

from core.research.research_models import SourceItem
from core.research.result_synthesizer import ResultSynthesizer


class _Stream:
    def __init__(self, text: str) -> None:
        self._text = text
        self._done = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._done:
            raise StopAsyncIteration
        self._done = True
        return type("Chunk", (), {"content": self._text})()

    async def aclose(self):
        return None


class _RoleLLM:
    def __init__(self, text: str):
        self._text = text

    async def chat(self, **_kwargs):
        return _Stream(self._text)


@pytest.mark.asyncio
async def test_returns_default_when_no_sources() -> None:
    synthesizer = ResultSynthesizer(role_llm=None)
    display, voice = await synthesizer.synthesize("query", [])
    assert "couldn't find" in display.lower()
    assert "couldn't find" in voice.lower()


@pytest.mark.asyncio
async def test_uses_llm_summary_when_available() -> None:
    payload = json.dumps(
        {
            "display": "**Summary**\n• Item [1]",
            "voice": "Short spoken summary.",
        }
    )
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/1",
            snippet="snippet",
            provider="tavily",
        )
    ]
    display, voice = await synthesizer.synthesize("query", sources)
    assert "Summary" in display
    assert voice == "Short spoken summary."


@pytest.mark.asyncio
async def test_non_json_fallback_uses_raw_for_display_and_voice() -> None:
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM("Plain text output."))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/1",
            snippet="snippet",
            provider="tavily",
        )
    ]
    display, voice = await synthesizer.synthesize("query", sources)
    assert display.startswith("**")
    assert "Plain text output." in display
    assert voice == "Plain text output."


@pytest.mark.asyncio
async def test_fallback_summary_uses_top_sources_on_llm_failure() -> None:
    bad_llm = type("BadLLM", (), {"chat": AsyncMock(side_effect=RuntimeError("fail"))})()
    synthesizer = ResultSynthesizer(role_llm=bad_llm)
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/1",
            snippet="first snippet",
            provider="tavily",
        ),
        SourceItem.from_values(
            title="S2",
            url="https://example.com/2",
            snippet="second snippet",
            provider="serper",
        ),
    ]
    display, voice = await synthesizer.synthesize("query", sources)
    assert "S1" in display
    assert "S2" in display
    assert display == voice


@pytest.mark.asyncio
async def test_repairs_json_leak_in_display_field() -> None:
    payload = json.dumps(
        {
            "display": json.dumps(
                {
                    "headline": "AI agents are shipping faster across teams.",
                    "impact": "Companies are adopting agent workflows in production.",
                }
            ),
            "voice": "AI agents are moving from pilots to production adoption.",
        }
    )
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/1",
            snippet="snippet",
            provider="tavily",
        )
    ]

    display, voice = await synthesizer.synthesize("latest ai agent news", sources)

    assert display.startswith("**")
    assert "🔹" in display
    assert "headline" in display.lower()
    assert voice == "AI agents are moving from pilots to production adoption."


@pytest.mark.asyncio
async def test_prepends_bold_header_when_missing() -> None:
    payload = json.dumps(
        {
            "display": "Key point one\n🔹 Key point two",
            "voice": "One clean spoken sentence.",
        }
    )
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/1",
            snippet="snippet",
            provider="tavily",
        )
    ]

    display, voice = await synthesizer.synthesize("query", sources)

    assert display.startswith("**")
    assert "Key point one" in display
    assert voice == "One clean spoken sentence."


@pytest.mark.asyncio
async def test_voice_cleanup_is_tts_safe_and_adaptive() -> None:
    payload = json.dumps(
        {
            "display": "**AI Update**\n🔹 Item one\nSources: [1]",
            "voice": (
                "**Latest AI update:** [1] New model launched today with faster inference. "
                "It also improved safety checks for production teams. "
                "This trailing sentence should be truncated."
            ),
        }
    )
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/1",
            snippet="snippet",
            provider="tavily",
        )
    ]

    _display, voice = await synthesizer.synthesize("latest ai update", sources)

    assert "**" not in voice
    assert "[1]" not in voice
    assert len(voice) <= 150
    assert voice.endswith(".")
    sentence_count = len([s for s in voice.split(".") if s.strip()])
    assert sentence_count <= 2


@pytest.mark.asyncio
async def test_synthesizer_salvage_prefers_voice_line_over_json_value() -> None:
    payload = """
**Current Prime Ministers**
{"India": "Narendra Modi", "United Kingdom": "Keir Starmer"}
voice: The current prime minister of India is Narendra Modi and he has served since 2014.
""".strip()
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/pm",
            snippet="Narendra Modi is the prime minister of India.",
            provider="tavily",
        )
    ]

    _display, voice = await synthesizer.synthesize("who is the prime minister of india", sources)

    assert voice.startswith("The current prime minister of India is Narendra Modi")
    assert len(voice) > 30


@pytest.mark.asyncio
async def test_synthesizer_fallbacks_to_json_voice_when_voice_line_missing() -> None:
    payload = """
**Company Summary**
{"display":"**OpenAI Leadership**\\n🔹 Sam Altman is the CEO.\\nSources: [1]","voice":"Sam Altman is the CEO of OpenAI."}
""".strip()
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/openai",
            snippet="Sam Altman is CEO.",
            provider="tavily",
        )
    ]

    _display, voice = await synthesizer.synthesize("who is the ceo of openai", sources)

    assert voice == "Sam Altman is the CEO of OpenAI."
    assert len(voice) > 25


@pytest.mark.asyncio
async def test_synthesizer_fallbacks_to_display_sentence_when_voice_too_short() -> None:
    payload = json.dumps(
        {
            "display": "Narendra Modi is the prime minister of India and has held office since 2014.",
            "voice": "Narendra Modi.",
        }
    )
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/modi",
            snippet="Narendra Modi is PM of India.",
            provider="tavily",
        )
    ]

    _display, voice = await synthesizer.synthesize("who is the prime minister of india", sources)

    assert voice != "Narendra Modi."
    assert "prime minister of India" in voice
    assert len(voice) > 25


@pytest.mark.asyncio
async def test_display_sentence_fallback_does_not_include_json_keys_in_voice() -> None:
    payload = """
**Current Prime Minister of India**
"display": Current Prime Minister of India, "voice": "The current prime minister of India is Narendra Modi."
Sources: [1]
""".strip()
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/pm",
            snippet="Narendra Modi is the prime minister of India.",
            provider="tavily",
        )
    ]

    _display, voice = await synthesizer.synthesize("who is the prime minister of india", sources)

    assert '"display":' not in voice.lower()
    assert '"voice":' not in voice.lower()
    assert "{" not in voice
    assert "}" not in voice


def test_voice_from_display_removes_sources_and_bullets() -> None:
    display = """**OpenAI Leadership**
🔹 Sam Altman is the CEO of OpenAI.
🔹 The company focuses on AI research.
Sources: [1] [2]
""".strip()

    voice = ResultSynthesizer._voice_from_display(display)

    assert "Sources:" not in voice
    assert "🔹" not in voice
    assert "Sam Altman is the CEO of OpenAI." in voice


@pytest.mark.asyncio
async def test_salvage_rejects_json_like_voice_and_uses_display_sentence() -> None:
    payload = """
**Current Prime Minister**
{"display":"**Current Prime Minister**\\n🔹 Narendra Modi is the current prime minister of India.\\nSources: [1]","voice":"\\"display\\": current prime minister, \\"voice\\": Narendra Modi."}
""".strip()
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/pm",
            snippet="Narendra Modi is the current prime minister of India.",
            provider="tavily",
        )
    ]

    _display, voice = await synthesizer.synthesize("who is the prime minister of india", sources)

    assert '"display":' not in voice.lower()
    assert '"voice":' not in voice.lower()
    assert "Narendra Modi is the current prime minister of India" in voice


@pytest.mark.asyncio
async def test_deep_voice_mode_allows_multi_sentence_summary() -> None:
    payload = json.dumps(
        {
            "display": "**Iran Market Impact**\n🔹 Oil volatility rose.\nSources: [1] [2]",
            "voice": (
                "Tensions between Iran and the United States have increased energy risk premiums. "
                "Oil and gold prices tend to react first due to supply and safety-demand concerns. "
                "Currency markets can also reprice quickly as risk sentiment changes."
            ),
        }
    )
    synthesizer = ResultSynthesizer(role_llm=_RoleLLM(payload))
    sources = [
        SourceItem.from_values(
            title="S1",
            url="https://example.com/market",
            snippet="Market volatility increased.",
            provider="tavily",
        )
    ]

    _display, voice = await synthesizer.synthesize(
        "give me a detailed report on market impact",
        sources,
        voice_mode="deep",
    )

    sentence_count = len([s for s in voice.split(".") if s.strip()])
    assert sentence_count >= 3
    assert len(voice) <= 900
