"""Constants extracted from AgentOrchestrator for readability and size control."""
from __future__ import annotations

import re

CONVERSATIONAL_MEMORY_TRIGGERS = (
    r"\b(remember|recall|remind me|earlier|last time|you said|i said|i told you|i asked)\b",
    r"\b(my name|my preference|my usual|what do i|who am i)\b",
    r"\b(what did (i|we|you))\b",
    r"\b(do you know|do you remember)\b",
)
RECALL_EXCLUSION_PATTERNS = (
    r"\bwhat\s+did\s+i\s+ask\b",
    r"\bwhat\s+did\s+i\s+say\b",
    r"\bdid\s+i\s+ask\b",
    r"\bdid\s+i\s+say\b",
    r"\bi\s+told\s+you\b",
    r"\byou\s+said\b",
    r"\bwe\s+discussed\b",
)
RECALL_EXCLUDED_TOOLS = {"web_search", "get_current_datetime", "get_current_date"}
TASK_COMPLETION_PATTERNS = (
    r"\bi completed(?: the)? action\b",
    r"\baction cancelled\b",
    r"\btask done\b",
    r"\btask completed\b",
)
TOOL_ERROR_HINT_PATTERN = re.compile(
    r"(traceback|exception|error executing command|timed out|timeout|failed|permission denied|access denied|blocked)",
    flags=re.IGNORECASE,
)
REPORT_EXPORT_PATTERNS = (
    r"\b(save|export)\s+(it|this|that|report|document|file)?\s*(to|in)?\s*(my\s+)?downloads\b",
    r"\b(save|export)\s+(as|into)\s+(docx|document|file)\b",
    r"\b(save|export|write)\s+.*\b(report|document|docx)\b.*\b(downloads|file)\b",
    r"\b(create|generate|prepare)\s+(a\s+)?(report|document|doc)\b.*\b(save|export)\b",
)
REPORT_EXPORT_KEYWORDS = (
    "save to downloads",
    "save it in my downloads",
    "save in my downloads",
    "export report",
    "save as docx",
    "save document",
)
DEEP_RESEARCH_KEYWORDS = (
    "report",
    "in depth",
    "in-depth",
    "detailed",
    "full analysis",
    "thorough",
    "full report",
)
MEDIA_PATTERNS = (
    r"\bplay\s+.+",
    r"\bsearch\s+.+\b(song|music|track|playlist|video)\b",
    r"\bqueue\b",
    r"\brecommend\b",
    r"\bsuggest\b.+\bmusic\b",
    r"\bwhat(?:'s| is)\s+playing\b",
    r"\byoutube\b",
    r"\bspotify\b",
)
MEDIA_EXCLUDE_PATTERNS = (
    r"\bwhat time is it\b",
    r"^\s*open\s+\w+",
    r"\b(open|close)\s+(firefox|chrome|calculator|folder|downloads)\b",
    r"\b(next|skip|previous|pause|resume|stop music)\b",
)
VOICE_TRANSCRIPTION_NORMALIZATIONS = {
    "diwnloads": "downloads",
    "downlods": "downloads",
    "downlodes": "downloads",
    "donwloads": "downloads",
    "downloades": "downloads",
}
VOICE_SHORT_COMMAND_ALLOWLIST = {
    "yes",
    "no",
    "ok",
    "okay",
    "sure",
    "stop",
    "pause",
    "resume",
    "play",
    "next",
    "continue",
    "cancel",
    "thanks",
    "thank you",
}
VOICE_CONTINUATION_MARKERS = {
    "just",
    "and",
    "but",
    "so",
    "then",
    "also",
    "that",
    "this",
    "it",
}
VOICE_ACTION_SECOND_TOKEN_ALLOWLIST = {
    "open",
    "close",
    "search",
    "play",
    "set",
    "take",
    "run",
    "start",
    "show",
    "list",
}
