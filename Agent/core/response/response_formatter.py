import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from core.response.agent_response import AgentResponse, Source, ToolInvocation


class ResponseFormatter:
    VOICE_TTS_MAX_CHARS_DIRECT = max(40, int(os.getenv("VOICE_TTS_MAX_CHARS_DIRECT", "140")))
    VOICE_TTS_MAX_SENTENCES_DIRECT = max(1, int(os.getenv("VOICE_TTS_MAX_SENTENCES_DIRECT", "1")))
    VOICE_TTS_MAX_CHARS_INFO = max(80, int(os.getenv("VOICE_TTS_MAX_CHARS_INFO", "300")))
    VOICE_TTS_MAX_SENTENCES_INFO = max(1, int(os.getenv("VOICE_TTS_MAX_SENTENCES_INFO", "2")))

    URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
    MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", re.IGNORECASE)
    CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
    INLINE_CODE_RE = re.compile(r"`([^`]+)`")
    LIST_MARKER_RE = re.compile(r"^\s*[-*+•]+\s*", re.MULTILINE)
    CITATION_RE = re.compile(r"\[\d+\]")
    RAW_JSON_HINT_RE = re.compile(r'(\{|\[|"[^"]+"\s*:)', re.IGNORECASE)
    SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
    CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
    INLINE_BACKTICK_RE = re.compile(r"`[^`]+`")
    MARKDOWN_DECORATION_RE = re.compile(r"[*_#~>]+")
    LIST_BULLET_RE = re.compile(r"^\s*[-•*]\s+", re.MULTILINE)
    LIST_NUMBER_RE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)

    @classmethod
    def _extract_json_blob(cls, text: str) -> Optional[str]:
        if not text:
            return None
        stripped = text.strip()

        # Handle fenced / prefixed outputs like:
        # ```json {...}``` or "json {...} trailing notes"
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"^\s*json\b\s*", "", stripped, flags=re.IGNORECASE)

        decoder = json.JSONDecoder()
        for idx, ch in enumerate(stripped):
            if ch not in "{[":
                continue
            candidate = stripped[idx:]
            try:
                _, end = decoder.raw_decode(candidate)
                return candidate[:end]
            except Exception:
                continue

        match = re.search(r"\{[\s\S]*?\}", stripped)
        if match:
            return match.group(0)
        return None

    @classmethod
    def parse_agent_response_json(cls, text: str) -> Optional[Dict[str, Any]]:
        blob = cls._extract_json_blob(text)
        if not blob:
            return None
        try:
            return json.loads(blob)
        except Exception:
            return None

    @classmethod
    def _looks_like_table(cls, text: str) -> bool:
        if not text or "|" not in text:
            return False
        rows = [line for line in text.splitlines() if "|" in line]
        return len(rows) >= 2

    @classmethod
    def sanitize_display_text(cls, text: str) -> str:
        if not text:
            return ""
        cleaned = text
        cleaned = re.sub(
            r"<function>\s*[a-zA-Z_][a-zA-Z0-9_]*\s*(?:\{.*?\})?\s*</function>",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
        cleaned = cls.MARKDOWN_LINK_RE.sub(r"\1", cleaned)
        cleaned = cls.URL_RE.sub("", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = cleaned.strip()
        return cleaned

    @classmethod
    def sanitize_voice_text(cls, text: str) -> str:
        if not text:
            return ""
        if cls._looks_like_table(text):
            return "I shared a table in the chat."
        cleaned = text
        cleaned = cls.MARKDOWN_LINK_RE.sub(r"\1", cleaned)
        cleaned = cls.CODE_BLOCK_RE.sub(" ", cleaned)
        cleaned = cls.INLINE_CODE_RE.sub(r"\1", cleaned)
        cleaned = cls.URL_RE.sub("", cleaned)
        cleaned = cls.LIST_MARKER_RE.sub("", cleaned)
        cleaned = cls.CITATION_RE.sub("", cleaned)
        cleaned = re.sub(r"[#*_>`]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        shortened = " ".join(sentences[:2]).strip()
        if len(shortened) > 320:
            shortened = shortened[:317].rstrip() + "..."
        return shortened

    @classmethod
    def _truncate_by_word_boundary(cls, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        clipped = text[:max_chars]
        last_space = clipped.rfind(" ")
        if last_space > max_chars // 2:
            clipped = clipped[:last_space]
        clipped = clipped.rstrip(".,;:")
        return f"{clipped}."

    @classmethod
    def to_voice_brief(
        cls,
        text: str,
        intent_type: str = "informational",
        max_chars_direct: Optional[int] = None,
        max_sentences_direct: Optional[int] = None,
        max_chars_info: Optional[int] = None,
        max_sentences_info: Optional[int] = None,
    ) -> str:
        """
        Reduce text to a deterministic, voice-safe brief response.
        """
        if intent_type == "fast_path":
            return (text or "").strip() or "Done."

        max_chars_direct = max_chars_direct or cls.VOICE_TTS_MAX_CHARS_DIRECT
        max_sentences_direct = max_sentences_direct or cls.VOICE_TTS_MAX_SENTENCES_DIRECT
        max_chars_info = max_chars_info or cls.VOICE_TTS_MAX_CHARS_INFO
        max_sentences_info = max_sentences_info or cls.VOICE_TTS_MAX_SENTENCES_INFO

        cleaned = text or ""
        cleaned = cls.CODE_FENCE_RE.sub("", cleaned)
        cleaned = cls.INLINE_BACKTICK_RE.sub("", cleaned)
        cleaned = cls.MARKDOWN_DECORATION_RE.sub("", cleaned)
        cleaned = cls.URL_RE.sub("", cleaned)
        cleaned = re.sub(r"www\.\S+", "", cleaned, flags=re.IGNORECASE)
        cleaned = cls.LIST_BULLET_RE.sub("", cleaned)
        cleaned = cls.LIST_NUMBER_RE.sub("", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return "Done."

        sentences = [s.strip() for s in cls.SENTENCE_SPLIT_RE.split(cleaned) if s.strip()]
        if intent_type == "direct_action":
            max_sentences = max_sentences_direct
            max_chars = max_chars_direct
        else:
            max_sentences = max_sentences_info
            max_chars = max_chars_info

        brief = " ".join(sentences[:max_sentences]) if sentences else cleaned
        brief = brief.strip()
        if not brief:
            return "Done."
        if len(brief) > max_chars:
            brief = cls._truncate_by_word_boundary(brief, max_chars)
        return brief or "Done."

    @classmethod
    def _is_raw_jsonish(cls, text: str) -> bool:
        if not text:
            return False
        return bool(cls.RAW_JSON_HINT_RE.search(text))

    @classmethod
    def _finalize_display_candidate(cls, text: str) -> Optional[str]:
        if not text:
            return None
        cleaned = cls.sanitize_voice_text(cls.sanitize_display_text(text))
        if not cleaned:
            return None
        if cls._is_raw_jsonish(cleaned):
            return None
        if len(cleaned) > 200:
            cleaned = cleaned[:200].rstrip()
        return cleaned or None

    @classmethod
    def extract_display_candidate(
        cls,
        structured_data: Optional[Dict[str, Any]],
        tool_name: str,
    ) -> Optional[str]:
        if not isinstance(structured_data, dict):
            return None
        tool = (tool_name or "").strip().lower()

        if tool == "web_search":
            summary = structured_data.get("summary")
            if isinstance(summary, str):
                value = cls._finalize_display_candidate(summary)
                if value:
                    return value
            results = structured_data.get("results")
            if isinstance(results, list) and results:
                first = results[0] if isinstance(results[0], dict) else {}
                snippet = first.get("snippet")
                if isinstance(snippet, str):
                    return cls._finalize_display_candidate(snippet)
            return None

        if tool == "get_weather":
            summary = structured_data.get("summary")
            if isinstance(summary, str):
                return cls._finalize_display_candidate(summary)
            return None

        if tool == "open_app":
            app_name = str(structured_data.get("app_name") or "").strip(" .")
            if app_name:
                return cls._finalize_display_candidate(f"Opened {app_name}.")
            return None

        if tool == "open_folder":
            folder_name = str(
                structured_data.get("folder_name")
                or structured_data.get("folder_key")
                or ""
            ).strip(" .")
            if folder_name:
                return cls._finalize_display_candidate(f"Opened {folder_name} folder.")
            return None

        if tool in {"set_alarm", "set_reminder"}:
            confirmation = structured_data.get("confirmation_text")
            if isinstance(confirmation, str):
                return cls._finalize_display_candidate(confirmation)
            return None

        if tool in {"media_next", "media_previous", "media_play_pause", "media_stop"}:
            status = structured_data.get("status_message")
            if isinstance(status, str):
                return cls._finalize_display_candidate(status)
            return None

        return None

    @classmethod
    def ensure_citations(cls, text: str, sources: Optional[List[Source]]) -> str:
        if not sources:
            return text
        if cls.CITATION_RE.search(text):
            return text
        markers = " ".join([f"[{idx + 1}]" for idx in range(len(sources))])
        return f"{text} {markers}"

    @classmethod
    def derive_sources(cls, structured_data: Optional[Dict[str, Any]]) -> List[Source]:
        if not structured_data:
            return []
        results = structured_data.get("results")
        if not isinstance(results, list):
            return []
        sources = []
        for item in results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "Source")
            url = str(item.get("url") or item.get("href") or "").strip()
            if not url:
                continue
            snippet = item.get("snippet") or item.get("body")
            sources.append(Source(title=title, url=url, snippet=snippet))
        return sources

    @classmethod
    def build_response(
        cls,
        display_text: str,
        voice_text: Optional[str] = None,
        sources: Optional[List[Source]] = None,
        tool_invocations: Optional[List[ToolInvocation]] = None,
        mode: str = "normal",
        memory_updated: bool = False,
        confidence: float = 0.5,
        structured_data: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        cleaned_display = cls.sanitize_display_text(display_text)
        sources = sources or cls.derive_sources(structured_data)
        if not cleaned_display:
            cleaned_display = cls.sanitize_display_text(voice_text or "")
        if not cleaned_display:
            cleaned_display = "I completed the action."
        cleaned_display = cls.ensure_citations(cleaned_display, sources)
        cleaned_voice = cls.sanitize_voice_text(voice_text or cleaned_display)
        if not cleaned_voice:
            cleaned_voice = cls.sanitize_voice_text(cleaned_display) or "I completed the action."
        return AgentResponse(
            display_text=cleaned_display,
            voice_text=cleaned_voice,
            sources=sources or None,
            tool_invocations=tool_invocations or None,
            mode=mode,
            memory_updated=memory_updated,
            confidence=confidence,
            structured_data=structured_data,
        )

    @classmethod
    def normalize_response(
        cls,
        raw: Any,
        *,
        sources: Optional[List[Source]] = None,
        tool_invocations: Optional[List[ToolInvocation]] = None,
        mode: str = "normal",
        memory_updated: bool = False,
        confidence: float = 0.5,
        structured_data: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        if isinstance(raw, AgentResponse):
            return raw
        if isinstance(raw, dict):
            display = raw.get("display_text") or raw.get("content") or raw.get("text") or ""
            voice = raw.get("voice_text")
            resp_sources = raw.get("sources")
            if resp_sources and not sources:
                sources = [Source(**s) if isinstance(s, dict) else s for s in resp_sources]
            return cls.build_response(
                display_text=display,
                voice_text=voice,
                sources=sources,
                tool_invocations=tool_invocations or raw.get("tool_invocations"),
                mode=raw.get("mode", mode),
                memory_updated=raw.get("memory_updated", memory_updated),
                confidence=float(raw.get("confidence", confidence)),
                structured_data=structured_data or raw.get("structured_data"),
            )
        if isinstance(raw, str):
            parsed = cls.parse_agent_response_json(raw)
            if parsed:
                return cls.normalize_response(
                    parsed,
                    sources=sources,
                    tool_invocations=tool_invocations,
                    mode=mode,
                    memory_updated=memory_updated,
                    confidence=confidence,
                    structured_data=structured_data,
                )
            return cls.build_response(
                display_text=raw,
                voice_text=None,
                sources=sources,
                tool_invocations=tool_invocations,
                mode=mode,
                memory_updated=memory_updated,
                confidence=confidence,
                structured_data=structured_data,
            )
        return cls.build_response(
            display_text=str(raw),
            voice_text=None,
            sources=sources,
            tool_invocations=tool_invocations,
            mode=mode,
            memory_updated=memory_updated,
            confidence=confidence,
            structured_data=structured_data,
        )
