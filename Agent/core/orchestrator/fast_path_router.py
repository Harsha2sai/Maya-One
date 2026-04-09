"""Deterministic fast-path tool intent detection."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DirectToolIntent:
    tool: Optional[str]
    args: Dict[str, Any]
    template: str
    group: str


class FastPathRouter:
    """Owns deterministic fast-path routing for high-frequency tool intents."""

    def __init__(
        self,
        *,
        turn_state: Dict[str, Any],
        parse_multi_app_fn: Callable[[str], List[str]],
        is_recall_exclusion_intent_fn: Callable[[str], bool],
        resolve_active_subject_fn: Optional[Callable[[], str]] = None,
    ) -> None:
        self._turn_state = turn_state
        self._parse_multi_app = parse_multi_app_fn
        self._is_recall_exclusion_intent = is_recall_exclusion_intent_fn
        self._resolve_active_subject = resolve_active_subject_fn or (lambda: "")

    _YOUTUBE_ALIASES = {"youtube", "yt"}
    _SEARCH_PRONOUN_TOKENS = {"it", "that", "this", "them", "they", "him", "her"}
    _SEARCH_FILLER_TOKENS = {"about", "for", "on", "in", "using", "the", "a", "an"}

    def _extract_platform_search_request(self, normalized: str) -> Optional[Dict[str, Any]]:
        text = str(normalized or "").strip().lower()
        if not text:
            return None

        patterns = (
            r"^(?:search|find|lookup|look up)\s+(?:on|in|using)\s+(youtube|yt)\s*(?:for|about)?\s*(.*)$",
            r"^(?:search|find|lookup|look up)\s+(youtube|yt)\s+(?:for|about)\s+(.+)$",
            r"^(?:youtube|yt)\s+search\s+(?:for|about)\s+(.+)$",
            r"^(?:open|go to)\s+(?:the\s+)?(youtube|yt)\s+(?:and|then)?\s*(?:search|find|lookup|look up)\s*(?:for|about)?\s*(.*)$",
            # New patterns for natural video/song search phrases
            r"^(?:open|play|show)\s+(?:videos?|clips?|songs?|music|tracks?)\s+(?:about|on|of|by|for)\s+(.+?)\s+(?:in|on)\s+(youtube|yt)$",
            r"^(?:open|play|show)\s+(?:videos?|clips?|songs?|music|tracks?)\s+(?:in|on)\s+(youtube|yt)\s+(?:about|on|of|by|for)\s+(.+)$",
            r"^(?:videos?|clips?|songs?|music|tracks?)\s+(?:about|on|of|by|for)\s+(.+?)\s+(?:in|on)\s+(youtube|yt)$",
        )
        for pattern in patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if not match:
                continue
            if len(match.groups()) == 1:
                platform = "youtube"
                query = str(match.group(1) or "").strip()
            else:
                # Determine which group is platform and which is query
                g1 = str(match.group(1) or "").strip().lower()
                g2 = str(match.group(2) or "").strip()
                if g1 in self._YOUTUBE_ALIASES:
                    platform = g1
                    query = g2
                elif g2 in self._YOUTUBE_ALIASES:
                    platform = g2
                    query = g1
                else:
                    # Default: assume group 1 is platform
                    platform = g1
                    query = g2
            if platform not in self._YOUTUBE_ALIASES:
                continue
            if not query:
                return {
                    "platform": "youtube",
                    "query": "",
                    "query_is_pronoun_only": True,
                }
            query_tokens = re.findall(r"[a-z0-9']+", query.lower())
            has_content_token = any(token not in self._SEARCH_FILLER_TOKENS for token in query_tokens)
            pronoun_only = bool(query_tokens) and all(
                token in (self._SEARCH_PRONOUN_TOKENS | self._SEARCH_FILLER_TOKENS)
                for token in query_tokens
            )
            return {
                "platform": "youtube",
                "query": query,
                "query_is_pronoun_only": pronoun_only or not has_content_token,
            }
        return None

    def detect_direct_tool_intent(
        self,
        message: str,
        origin: str = "chat",
    ) -> Optional[DirectToolIntent]:
        """
        Deterministic fast-path for high-frequency queries.
        Avoids LLM roundtrip and prevents 'thinking forever' on trivial time/date asks.
        """
        text = (message or "").strip().lower()
        normalized = re.sub(r"\s+", " ", text).strip()
        normalized = re.sub(r"[.,!?]+", "", normalized).strip()
        logger.debug(
            "fast_path_classification_input origin=%s input_length=%d has_bootstrap_marker=%s preview='%s'",
            origin,
            len(message or ""),
            "\n\ncurrent user message:\n" in text,
            (message or "")[:80].replace("\n", "\\n"),
        )

        if self._is_recall_exclusion_intent(text):
            logger.info("🧭 routing_mode=planner recall_exclusion=true origin=%s", origin)
            return None

        time_patterns = (
            r"\bwhat(?:'s| is)?\s+(?:the\s+)?time\b",
            r"\bcurrent\s+time\b",
            r"\btime\s+now\b",
            r"\bwhat\s+time\s+is\s+it\b",
            r"\bcan you tell me the time\b",
            r"\bdo you know (?:what|the) time\b",
            r"\btell me the time\b",
            r"\bwhat(?:'s| is) the (?:current )?time\b",
            r"\btime (?:is it|now)\b",
        )
        if any(re.search(p, text) for p in time_patterns):
            return DirectToolIntent("get_time", {}, "Here's the current time.", "time")

        date_patterns = (
            r"\bwhat(?:'s| is)?\s+(?:the\s+)?date\b",
            r"\btoday'?s\s+date\b",
            r"\bwhat\s+day\s+is\s+it\b",
        )
        if any(re.search(p, text) for p in date_patterns):
            return DirectToolIntent("get_date", {}, "Here's today's date.", "time")

        raw_message = (message or "").strip()
        note_create_match = re.match(
            r"^\s*create\s+(?:a\s+)?note(?:\s+titled)?\s+(?P<title>.+?)\s+with\s+content\s+(?P<content>.+)\s*$",
            raw_message,
            re.IGNORECASE,
        )
        if note_create_match:
            title = note_create_match.group("title").strip().strip("\"'")
            content = note_create_match.group("content").strip().strip("\"'")
            if title and content:
                return DirectToolIntent(
                    "create_note",
                    {"title": title, "content": content},
                    f"I've created note '{title}'.",
                    "notes",
                )

        note_read_match = re.match(
            r"^\s*(?:read|show)\s+(?:my\s+)?note\s+(?P<title>.+)\s*$",
            raw_message,
            re.IGNORECASE,
        )
        if note_read_match:
            title = note_read_match.group("title").strip().strip("\"'")
            if title:
                return DirectToolIntent("read_note", {"title": title}, f"Reading note '{title}'.", "notes")

        note_delete_match = re.match(
            r"^\s*delete\s+(?:my\s+)?note\s+(?P<title>.+)\s*$",
            raw_message,
            re.IGNORECASE,
        )
        if note_delete_match:
            title = note_delete_match.group("title").strip().strip("\"'")
            if title:
                return DirectToolIntent("delete_note", {"title": title}, f"Deleted note '{title}'.", "notes")

        if re.match(r"^\s*(?:list|show)\s+(?:my\s+)?notes\s*$", raw_message, re.IGNORECASE):
            return DirectToolIntent("list_notes", {}, "Here are your notes.", "notes")

        if re.search(r"\b(next|skip|change)\b.{0,15}\b(song|track|music)\b", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl next"}, "Next track.", "media")
        if re.search(r"\b(previous|prev|go back|last)\b.{0,15}\b(song|track|music)\b", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl previous"}, "Previous track.", "media")
        if re.match(r"^\s*play\s+next(?:\s+(?:song|track|music))?\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl next"}, "Next track.", "media")
        if re.match(
            r"^\s*play\s+previous(?:\s+(?:song|track|music))?\s*$",
            normalized,
            re.IGNORECASE,
        ):
            return DirectToolIntent("run_shell_command", {"command": "playerctl previous"}, "Previous track.", "media")
        if re.match(r"^\s*(pause|pause (the )?(music|song|playback))\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl pause"}, "Paused.", "media")
        if re.match(r"^\s*(resume|continue playing|resume music)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl play"}, "Playing.", "media")
        if re.match(r"^\s*(stop|stop music|stop song|stop playback)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl stop"}, "Stopped.", "media")
        if re.match(r"^\s*(volume up|increase volume|turn volume up|louder)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl volume 0.1+"}, "Volume up.", "media")
        if re.match(r"^\s*(volume down|decrease volume|turn volume down|quieter)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl volume 0.1-"}, "Volume down.", "media")
        if re.match(r"^\s*(mute|mute music|mute playback)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl volume 0.0"}, "Muted.", "media")
        volume_set = re.match(
            r"^\s*(?:set|change|adjust)(?:\s+the)?\s+volume(?:\s+to)?\s+(\d{1,3})\s*%?\s*$",
            normalized,
            re.IGNORECASE,
        )
        if volume_set:
            percent = max(0, min(100, int(volume_set.group(1))))
            return DirectToolIntent(
                "set_volume",
                {"percent": percent},
                f"Set volume to {percent}%.",
                "media",
            )

        platform_search = self._extract_platform_search_request(normalized)
        if platform_search:
            query = str(platform_search.get("query") or "").strip()
            query_is_pronoun_only = bool(platform_search.get("query_is_pronoun_only"))
            if query_is_pronoun_only:
                resolved_subject = str(self._resolve_active_subject() or "").strip()
                if resolved_subject:
                    query = resolved_subject
                else:
                    return DirectToolIntent(
                        None,
                        {},
                        "What topic should I search on YouTube?",
                        "youtube",
                    )
            if query:
                self._turn_state["last_search_target"] = "youtube"
                self._turn_state["last_search_query"] = query
                return DirectToolIntent(
                    "open_app",
                    {"app_name": f"youtube search for {query}"},
                    f"Searching YouTube for {query}.",
                    "youtube",
                )
        if re.match(r"^open youtube\s*$", normalized, re.IGNORECASE):
            self._turn_state["last_search_target"] = "youtube"
            return DirectToolIntent("open_app", {"app_name": "youtube"}, "Opening YouTube.", "youtube")

        folder_match = re.match(
            r"^open\s+(?:my\s+)?(downloads|documents|desktop|home|pictures|videos)(?:\s+folder)?\s*$",
            normalized,
            re.IGNORECASE,
        )
        if folder_match:
            folder = folder_match.group(1).strip().lower()
            home = os.path.expanduser("~")
            folder_map = {
                "downloads": os.path.join(home, "Downloads"),
                "documents": os.path.join(home, "Documents"),
                "desktop": os.path.join(home, "Desktop"),
                "home": home,
                "pictures": os.path.join(home, "Pictures"),
                "videos": os.path.join(home, "Videos"),
            }
            folder_path = folder_map.get(folder, home)
            return DirectToolIntent(
                "run_shell_command",
                {"command": f"xdg-open '{folder_path}'"},
                f"Opened {folder.capitalize()} folder.",
                "app",
            )

        open_app_patterns = (
            r"^\s*(?:open|launch|start)\s+(.+)$",
            r"^\s*open\s+the\s+(.+)$",
        )
        for pat in open_app_patterns:
            match = re.search(pat, text)
            if match:
                app_name = (match.group(1) or "").strip()
                if app_name:
                    multi_app_commands = self._parse_multi_app(app_name)
                    if multi_app_commands:
                        return DirectToolIntent(
                            "run_shell_command",
                            {"commands": multi_app_commands},
                            f"Opening {app_name}.",
                            "app",
                        )
                    return DirectToolIntent("open_app", {"app_name": app_name}, f"Opening {app_name}.", "app")

        close_app_patterns = (
            r"^\s*(?:close|quit|exit|stop)\s+(.+)$",
            r"^\s*close\s+the\s+(.+)$",
        )
        for pat in close_app_patterns:
            match = re.search(pat, text)
            if match:
                app_name = (match.group(1) or "").strip()
                if app_name:
                    return DirectToolIntent("close_app", {"app_name": app_name}, f"Closing {app_name}.", "app")

        return None
