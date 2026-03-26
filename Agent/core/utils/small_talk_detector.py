"""
Small Talk Detector

Detects trivial/small talk messages that don't require:
- Memory search
- Embeddings generation
- Complex planning

This reduces latency and token usage for simple greetings and chitchat.
"""

import re
from typing import Set

# Common small talk patterns (lowercase for matching)
SMALL_TALK_PATTERNS: Set[str] = {
    # Greetings
    "hi", "hello", "hey", "hi there", "hello there", "hey there",
    "good morning", "good afternoon", "good evening", "good night",
    "morning", "evening", "night",
    # Short variations
    "hii", "hiii", "heyy", "heyyy", "hiiii",
    "hiii", "hiiii", "hiiiii", "hey", "heey",
    "hhello", "heello", "helllo",
    # Casual check-ins
    "how are you", "how are you doing", "how's it going",
    "what's up", "sup", "whats up", "wassup", "what is up",
    "how's everything", "how are things",
    "how have you been", "how've you been",
    # Acknowledgments
    "ok", "okay", "kk", "k", "yes", "no", "yeah", "nah",
    "thanks", "thank you", "thx", "ty",
    "cool", "nice", "awesome", "great", "good", "wow",
    "bye", "goodbye", "see you", "cya", "later",
    # Filler
    "hmm", "uhh", "uh", "um", "ah", "oh", "eh",
}

# Regex patterns for more complex matches
SMALL_TALK_REGEX = [
    r'^(hi+|hello+|hey+)[!\.\s]*$',  # Repeated letters: hiii, heyyy
    r'^(yo|sup|wassup)[!\.\s]*$',     # Slang
    r'^[ok]+$',                        # just "ok" or "kkk"
    r'^(thanks?|thx|ty)[!\.\s]*$',   # variations of thanks
    r'^(bye+|cya|see ya)[!\.\s]*$',   # goodbyes
]

def is_small_talk(message: str, min_length: int = 4) -> bool:
    """
    Detect if a message is small talk that doesn't need memory search.

    Args:
        message: The user's message
        min_length: Minimum message length to be considered non-trivial (default 4)

    Returns:
        True if message is small talk, False otherwise

    Examples:
        >>> is_small_talk("hi")
        True
        >>> is_small_talk("hhhii")
        True
        >>> is_small_talk("what's the weather like in Tokyo")
        False
        >>> is_small_talk("create a task for me")
        False
    """
    if not message or not isinstance(message, str):
        return True  # Empty messages are trivial

    # Normalize: lowercase, strip whitespace
    normalized = message.strip().lower()

    # Rule 1: Very short messages (single words)
    if len(normalized) < min_length and normalized.isalpha():
        return True

    # Rule 2: Exact match in small talk patterns
    if normalized in SMALL_TALK_PATTERNS:
        return True

    # Rule 3: Regex pattern matching
    for pattern in SMALL_TALK_REGEX:
        if re.match(pattern, normalized):
            return True

    # Rule 4: Repeated single character (e.g., "hhhh", "aaaa")
    if len(set(normalized)) == 1 and len(normalized) <= 6:
        return True

    # Rule 5: Contains only greetings + punctuation
    # Split by punctuation and check if remaining words are all small talk
    words = re.split(r'[!\.\?\s,]+', normalized)
    words = [w for w in words if w]  # Remove empty strings
    if words and all(w in SMALL_TALK_PATTERNS for w in words):
        return True

    return False


def classify_message_type(message: str) -> str:
    """
    Classify a message into categories for routing decisions.

    Returns:
        - "small_talk": Trivial chat, no memory needed
        - "task_request": Likely needs planning
        - "informational": Might need memory/RAG
        - "action": Likely needs tools
    """
    if is_small_talk(message):
        return "small_talk"

    normalized = message.lower().strip()

    # Task keywords
    task_keywords = [
        "create", "make", "schedule", "plan", "set up", "start",
        "task", "remind", "reminder", "alarm", "todo",
        "buy", "purchase", "order", "get me", "find me"
    ]
    if any(kw in normalized for kw in task_keywords):
        return "task_request"

    # Action keywords (tools likely needed)
    action_keywords = [
        "send", "write", "call", "open", "close", "run",
        "execute", "search", "look up", "check", "update"
    ]
    if any(kw in normalized for kw in action_keywords):
        return "action"

    # Informational (might benefit from memory)
    info_keywords = [
        "what", "when", "where", "who", "why", "how",
        "tell me about", "do you remember", "did i", "have i"
    ]
    if any(kw in normalized for kw in info_keywords):
        return "informational"

    # Default
    return "general"
