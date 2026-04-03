from __future__ import annotations

import json
import logging
import re
from typing import Any, Tuple

from livekit.agents.llm import ChatContext, ChatMessage

from core.llm.llm_roles import LLMRole

from .research_models import SourceItem

logger = logging.getLogger(__name__)


class ResultSynthesizer:
    def __init__(self, role_llm: Any = None) -> None:
        self.role_llm = role_llm

    async def synthesize(
        self,
        query: str,
        sources: list[SourceItem] | None = None,
        *,
        snippets: list[dict[str, Any]] | None = None,
        voice_mode: str = "brief",
    ) -> Tuple[str, str]:
        if (not sources) and snippets:
            converted: list[SourceItem] = []
            for item in snippets:
                title = str((item or {}).get("title") or "Snippet").strip() or "Snippet"
                snippet = str(
                    (item or {}).get("snippet")
                    or (item or {}).get("content")
                    or (item or {}).get("text")
                    or ""
                ).strip()
                converted.append(
                    SourceItem.from_values(
                        title=title,
                        url=str((item or {}).get("url") or f"https://snippet.local/{title[:20]}"),
                        snippet=snippet,
                        provider=str((item or {}).get("provider") or "snippet"),
                    )
                )
            sources = converted

        sources = sources or []
        if not sources:
            default_msg = "I couldn't find enough reliable information right now."
            return default_msg, default_msg

        voice_mode = self._coerce_voice_mode(voice_mode)
        llm_display, llm_voice = await self._llm_summarize(
            query,
            sources,
            voice_mode=voice_mode,
        )
        if llm_display or llm_voice:
            display = self._repair_display(llm_display or llm_voice)
            voice = self._normalize_voice(
                llm_voice or llm_display,
                voice_mode=voice_mode,
            ) or self._normalize_voice(display, voice_mode=voice_mode)
            if self._is_voice_low_quality(voice):
                fallback_voice = self._voice_from_display(display, voice_mode=voice_mode)
                if fallback_voice and not self._is_voice_low_quality(fallback_voice):
                    voice = fallback_voice
            return display, voice

        top = sources[:3]
        sentences = [
            f"I found {len(sources)} relevant sources for '{query}'.",
        ]
        for src in top:
            snippet = src.snippet.strip() or "No preview available."
            sentences.append(f"{src.title}: {snippet}")
        fallback = " ".join(sentences)
        return fallback, fallback

    async def _llm_summarize(
        self,
        query: str,
        sources: list[SourceItem],
        *,
        voice_mode: str = "brief",
    ) -> Tuple[str, str]:
        if self.role_llm is None:
            return "", ""

        voice_mode = self._coerce_voice_mode(voice_mode)
        if voice_mode == "deep":
            voice_rules = (
                "- 3 to 5 sentences.\n"
                "- Plain spoken English only.\n"
                "- Zero bullets, zero emoji, zero markdown, zero source numbers.\n"
                "- Explain key context, impacts, and uncertainty clearly.\n"
                "- Keep under 900 characters."
            )
            voice_instruction = (
                "voice must be 3 to 5 sentences of plain spoken English under 900 characters."
            )
        else:
            voice_rules = (
                "- EXACTLY 1 sentence. Never 2. Never more.\n"
                "- Plain spoken English only.\n"
                "- Zero bullets, zero emoji, zero markdown, zero source numbers.\n"
                "- Must sound like a human speaking, not reading a list.\n"
                "- If you write more than one sentence, you have failed this rule."
            )
            voice_instruction = "voice must be exactly 1 sentence of plain spoken English."

        sources_text = "\n".join(
            [f"- {s.title} | {s.url} | {s.snippet}" for s in sources[:8]]
        )
        system_prompt = f"""
You are a research synthesizer. You MUST return valid JSON only.
No preamble. No explanation. No markdown code fences. Just JSON.

Return exactly this structure:
{{
  "display": "<formatted answer>",
  "voice": "<spoken summary>"
}}

DISPLAY rules (strictly enforced):
- Line 1: MUST be a bold header using ** like: **Topic Name - Key Findings**
- Lines 2-6: emoji bullet points only (use 🔹 or ✅ or 🚀)
- Each bullet: one concise fact, max 15 words
- Final line: Sources: [1] [2] [3]
- Absolutely no prose paragraphs in display

VOICE rules (strictly enforced):
- {voice_rules}
""".strip()
        user_prompt = f"""
Query: {query}
Sources: {sources_text}

Return JSON only. display must start with a ** bold header.
{voice_instruction}
""".strip()
        chat_ctx = ChatContext(
            [
                ChatMessage(role="system", content=[system_prompt]),
                ChatMessage(role="user", content=[user_prompt]),
            ]
        )

        try:
            stream = await self.role_llm.chat(
                role=LLMRole.CHAT,
                chat_ctx=chat_ctx,
                tools=[],
                tool_choice="none",
            )
            text = await self._stream_to_text(stream)
            display, voice = self._parse_dual_output(text, voice_mode=voice_mode)
            if display and voice and not self._has_json_voice_signatures(voice):
                logger.info(
                    "research_synthesizer_parse_mode=%s research_synthesizer_voice_len=%s",
                    "json",
                    len(voice or ""),
                )
                return display, voice
            display, voice, parse_mode = self._salvage_raw_output(
                text,
                voice_mode=voice_mode,
            )
            if display and voice:
                logger.info(
                    "research_synthesizer_parse_mode=%s research_synthesizer_voice_len=%s",
                    parse_mode,
                    len(voice or ""),
                )
                return display, voice
            raw = text.strip()
            logger.info(
                "research_synthesizer_parse_mode=%s research_synthesizer_voice_len=%s",
                "raw_fallback",
                len(raw or ""),
            )
            return raw, raw
        except Exception as e:
            logger.info("research_synthesizer_llm_fallback reason=%s", e)
            return "", ""

    @staticmethod
    def _parse_dual_output(raw_text: str, *, voice_mode: str = "brief") -> Tuple[str, str]:
        raw = ResultSynthesizer._strip_code_fences(raw_text)
        if not raw:
            return "", ""
        try:
            payload = json.loads(raw)
        except Exception:
            return "", ""
        if not isinstance(payload, dict):
            return "", ""
        display = ResultSynthesizer._normalize_display(str(payload.get("display") or ""))
        voice = ResultSynthesizer._normalize_voice(
            str(payload.get("voice") or ""),
            voice_mode=voice_mode,
        )
        if not display or not voice:
            return "", ""
        return display, voice

    @staticmethod
    def _strip_code_fences(raw_text: Any) -> str:
        raw = str(raw_text or "").strip()
        if not raw.startswith("```"):
            return raw
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        return raw.strip()

    @staticmethod
    def _normalize_display(display: str) -> str:
        cleaned = ResultSynthesizer._repair_display(display)
        if not cleaned:
            return ""
        if not cleaned.startswith("**"):
            cleaned = f"**Research Summary**\n{cleaned}"
        return cleaned

    @staticmethod
    def _repair_display(text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""

        if cleaned.startswith(("{", "[")):
            try:
                payload = json.loads(cleaned)
                lines: list[str] = []
                if isinstance(payload, dict):
                    for key, value in payload.items():
                        value_text = ResultSynthesizer._json_value_to_text(value)
                        if value_text:
                            lines.append(f"🔹 **{str(key).strip()}**: {value_text}")
                elif isinstance(payload, list):
                    for item in payload:
                        item_text = ResultSynthesizer._json_value_to_text(item)
                        if item_text:
                            lines.append(f"🔹 {item_text}")
                cleaned = "\n".join(lines) if lines else cleaned
            except Exception:
                cleaned = re.sub(r'[{}\[\]"]', "", cleaned).strip()

        if cleaned and not cleaned.startswith("**"):
            cleaned = f"**Results**\n{cleaned}"
        return cleaned

    @staticmethod
    def _json_value_to_text(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        if value is None:
            return ""
        if isinstance(value, list):
            return ", ".join(
                item for item in (ResultSynthesizer._json_value_to_text(v) for v in value) if item
            )
        if isinstance(value, dict):
            parts = []
            for k, v in value.items():
                v_text = ResultSynthesizer._json_value_to_text(v)
                if v_text:
                    parts.append(f"{k}: {v_text}")
            return "; ".join(parts)
        return str(value).strip()

    @staticmethod
    def _coerce_voice_mode(voice_mode: str) -> str:
        normalized = str(voice_mode or "brief").strip().lower()
        if normalized not in {"brief", "deep"}:
            return "brief"
        return normalized

    @staticmethod
    def _normalize_voice(voice: str, *, voice_mode: str = "brief") -> str:
        voice_mode = ResultSynthesizer._coerce_voice_mode(voice_mode)
        cleaned = str(voice or "").strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
        cleaned = re.sub(r"[*_`#>~\-]", "", cleaned)
        cleaned = re.sub(r"[•🔹✅🚀]", "", cleaned)
        cleaned = re.sub(r"[(){}]", "", cleaned)
        cleaned = re.sub(r"\b\d+\.\s*", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return ""

        sentences = [
            segment.strip()
            for segment in re.split(r"(?<=[.!?])\s+", cleaned)
            if segment.strip()
        ]
        if not sentences:
            sentences = [cleaned]

        if voice_mode == "deep":
            max_sentences = 5
            max_chars = 900
        else:
            lower = cleaned.lower()
            complex_markers = (
                "latest",
                "recent",
                "today",
                "right now",
                "update",
                "news",
                "because",
                "however",
                "while",
            )
            is_complex = len(cleaned) > 90 or sum(1 for token in complex_markers if token in lower) >= 1
            max_sentences = 2 if is_complex else 1
            max_chars = 150

        cleaned = " ".join(sentences[:max_sentences]).strip()

        if len(cleaned) > max_chars:
            trimmed = cleaned[:max_chars].rsplit(" ", 1)[0].strip()
            cleaned = trimmed if trimmed else cleaned[:max_chars].strip()
        cleaned = cleaned.rstrip(" ,;:")
        if cleaned and cleaned[-1] not in ".!?":
            cleaned = f"{cleaned}."
        return cleaned

    @staticmethod
    def _extract_voice_line(raw: str) -> str:
        match = re.search(r"(?im)^\s*voice\s*:\s*(.+)\s*$", str(raw or ""))
        if not match:
            return ""
        return str(match.group(1) or "").strip()

    @staticmethod
    def _is_voice_low_quality(voice: str) -> bool:
        cleaned = str(voice or "").strip()
        if not cleaned:
            return True
        if len(cleaned) < 25:
            return True
        verbs = (
            " is ",
            " are ",
            " was ",
            " were ",
            " has ",
            " have ",
            " had ",
            " does ",
            " do ",
            " did ",
            " can ",
            " will ",
            " leads ",
            " serves ",
            " founded ",
            " runs ",
            " means ",
            " refers ",
        )
        lower = f" {cleaned.lower()} "
        return not any(token in lower for token in verbs)

    @staticmethod
    def _has_json_voice_signatures(text: str) -> bool:
        sample = str(text or "")
        return bool(
            re.search(r'(?i)"?\b(display|voice)\b"?\s*:', sample)
            or re.search(r"[{}]", sample)
        )

    @staticmethod
    def _voice_from_display(display: str, *, voice_mode: str = "brief") -> str:
        text = str(display or "").strip()
        if not text:
            return ""
        lines = []
        for line in text.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if candidate.startswith("**") and candidate.endswith("**"):
                continue
            if re.match(r"(?i)^sources?\s*:", candidate):
                continue
            candidate = re.sub(r"^\s*[-*•🔹✅🚀]+\s*", "", candidate)
            lines.append(candidate)

        merged = " ".join(lines) if lines else text
        merged = re.sub(r'(?i)"?\b(display|voice)\b"?\s*:\s*', " ", merged)
        merged = re.sub(r"[{}\"]", " ", merged)
        merged = re.sub(r"\s+", " ", merged).strip()
        if not merged:
            return ""
        if ResultSynthesizer._coerce_voice_mode(voice_mode) == "deep":
            return ResultSynthesizer._normalize_voice(merged, voice_mode="deep")
        first_sentence = re.split(r"(?<=[.!?])\s+", merged, maxsplit=1)[0].strip()
        return ResultSynthesizer._normalize_voice(first_sentence or merged, voice_mode="brief")

    @staticmethod
    def _salvage_raw_output(raw_text: Any, *, voice_mode: str = "brief") -> Tuple[str, str, str]:
        raw = ResultSynthesizer._strip_code_fences(raw_text)
        if not raw:
            return "", "", "empty"

        header_match = re.search(r"(\*\*[^*\n]+\*\*)", raw)
        header = header_match.group(1).strip() if header_match else "**Research Summary**"

        voice_line = ResultSynthesizer._normalize_voice(
            ResultSynthesizer._extract_voice_line(raw),
            voice_mode=voice_mode,
        )

        json_payload = ResultSynthesizer._extract_first_json_object(raw)
        if isinstance(json_payload, dict):
            json_voice = ResultSynthesizer._normalize_voice(
                str(json_payload.get("voice") or ""),
                voice_mode=voice_mode,
            )
            if (
                voice_line
                and not ResultSynthesizer._is_voice_low_quality(voice_line)
                and not ResultSynthesizer._has_json_voice_signatures(voice_line)
            ):
                display_from_json = str(json_payload.get("display") or "")
                display = ResultSynthesizer._normalize_display(display_from_json or raw)
                return display, voice_line, "voice_line"
            if (
                json_voice
                and not ResultSynthesizer._is_voice_low_quality(json_voice)
                and not ResultSynthesizer._has_json_voice_signatures(json_voice)
            ):
                display_from_json = str(json_payload.get("display") or "")
                display = ResultSynthesizer._normalize_display(display_from_json or raw)
                return display, json_voice, "json_voice"
            bullet_texts = ResultSynthesizer._extract_bullet_texts(json_payload)
            if bullet_texts:
                bullets = [
                    f"🔹 {ResultSynthesizer._trim_words(text, 15)}" for text in bullet_texts[:5]
                ]
                source_count = min(3, max(1, len(bullet_texts)))
                sources = " ".join(f"[{idx}]" for idx in range(1, source_count + 1))
                display = "\n".join([header, *bullets, f"Sources: {sources}"])
                voice = ResultSynthesizer._voice_from_display(display, voice_mode=voice_mode)
                if (
                    voice
                    and not ResultSynthesizer._is_voice_low_quality(voice)
                    and not ResultSynthesizer._has_json_voice_signatures(voice)
                ):
                    return ResultSynthesizer._normalize_display(display), voice, "display_sentence"

        if json_payload is None and header_match is None:
            normalized_raw_voice = ResultSynthesizer._normalize_voice(raw, voice_mode=voice_mode)
            return raw, normalized_raw_voice or raw, "raw_passthrough"

        display = ResultSynthesizer._normalize_display(raw)
        voice = ResultSynthesizer._voice_from_display(display, voice_mode=voice_mode)
        if not voice or ResultSynthesizer._has_json_voice_signatures(voice):
            voice = ResultSynthesizer._normalize_voice(raw, voice_mode=voice_mode)
        return display, voice, "display_sentence"

    @staticmethod
    def _extract_first_json_object(raw: str) -> Any:
        start = raw.find("{")
        if start < 0:
            return None
        try:
            payload, _ = json.JSONDecoder().raw_decode(raw[start:])
            return payload
        except Exception:
            return None

    @staticmethod
    def _extract_bullet_texts(payload: Any) -> list[str]:
        texts: list[str] = []
        if isinstance(payload, dict):
            for key in ("Description", "description", "summary", "text", "title"):
                candidate = str(payload.get(key) or "").strip()
                if candidate:
                    texts.append(candidate)
                    break
            for value in payload.values():
                texts.extend(ResultSynthesizer._extract_bullet_texts(value))
        elif isinstance(payload, list):
            for item in payload:
                texts.extend(ResultSynthesizer._extract_bullet_texts(item))
        elif isinstance(payload, str) and payload.strip():
            texts.append(payload.strip())
        return texts

    @staticmethod
    def _trim_words(text: str, max_words: int) -> str:
        words = str(text or "").strip().split()
        if len(words) <= max_words:
            return " ".join(words)
        return " ".join(words[:max_words]).rstrip(".,;:") + "..."

    @staticmethod
    async def _stream_to_text(stream: Any) -> str:
        chunks: list[str] = []
        try:
            async for chunk in stream:
                if hasattr(chunk, "choices") and getattr(chunk, "choices", None):
                    delta = getattr(chunk.choices[0], "delta", None)
                    text = getattr(delta, "content", "") if delta is not None else ""
                elif hasattr(chunk, "delta") and getattr(chunk, "delta", None):
                    delta = chunk.delta
                    text = getattr(delta, "content", "")
                else:
                    text = str(getattr(chunk, "content", "") or "")
                if text:
                    chunks.append(text)
        finally:
            close_fn = getattr(stream, "aclose", None)
            if callable(close_fn):
                try:
                    await close_fn()
                except Exception:
                    pass
        return "".join(chunks)
