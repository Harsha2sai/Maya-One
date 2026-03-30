import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


class AgentRouter:
    ALLOWED_KEYS = {"identity", "media_play", "research", "system", "scheduling", "chat"}
    _USER_MEMORY_PATTERNS = (
        r"\bdo you know my name\b",
        r"\bwhat do you know about me\b",
        r"\bdo you remember\b",
        r"\bwhat have i told you\b",
        r"\bremember when i said\b",
        r"\bmy name is\b",
        r"\bwhat(?:'s| is)\s+my\s+name\b",
        r"\bremember my\b",
    )
    _IDENTITY_PATTERNS = (
        r"\bwhat(?:'s| is)\s+your\s+name\b",
        r"\bwho are you\b",
        r"\bwhat can you do\b",
        r"\bare you an ai\b",
        r"\btell me about yourself\b",
        r"\bwho\s+(?:made|created|built|developed)\s+you\b",
        r"\bwho\s+(?:is\s+)?your\s+(?:creator|developer|maker|author)\b",
        r"\bintroduce\s+yourself\b",
        r"\bwhat\s+are\s+you\b",
        r"\bwhere\s+(?:do\s+you\s+come\s+from|are\s+you\s+from)\b",
        r"\bwhat\s+(?:company|organization|team)\s+(?:made|built|created)\s+you\b",
    )
    _NOTE_PATTERNS = (
        r"\bread\s+my\s+note\b",
        r"\bdelete\s+my\s+note\b",
        r"\bshow\s+my\s+note\b",
        r"\blist\s+my\s+notes\b",
    )
    _RESEARCH_FRESHNESS_PATTERNS = (
        r"\bwho is (?:the )?(?:current )?(?:ceo|cto|cfo|president|founder|head|prime minister|chancellor|governor|mayor)\b",
        r"\bcurrent (?:ceo|cto|cfo|leader|president|head|prime minister|chancellor|governor|mayor)\b",
        r"\bwho (?:runs|leads|owns|heads)\b",
        r"\b(latest|recent|today|right now|this week)\b",
        r"\bnews\b",
    )
    _MEDIA_PLAY_PATTERNS = (
        r"\bplay\b",
        r"\bput on\b",
        r"\bstart playing\b",
        r"\bnext\s+(?:track|song|video)\b",
        r"\bskip\b",
        r"\bpause\b",
        r"\bresume\b",
    )
    _SCHEDULING_PATTERNS = (
        r"\bremind me\b",
        r"\bset (?:a )?reminder\b",
        r"\blist reminders\b",
        r"\bshow reminders\b",
        r"\bdelete reminder\b",
        r"\bset (?:an )?alarm\b",
        r"\blist alarms\b",
        r"\bshow alarms\b",
        r"\bdelete alarm\b",
        r"\bcalendar event\b",
        r"\bcalendar\b",
    )

    def __init__(self, llm_client: Any):
        self._llm = llm_client
        self._depth: Dict[str, int] = {}
        self.MAX_DEPTH = 3

    async def route(self, utterance: str, user_id: str) -> str:
        user_key = str(user_id or "anonymous")
        current = self._depth.get(user_key, 0)
        if current >= self.MAX_DEPTH:
            logger.warning("agent_depth_exceeded: %s at depth %s", user_key, current)
            self._depth[user_key] = 0
            return "chat"

        utterance_l = str(utterance or "").strip().lower()

        # 1. Deterministic overrides — run BEFORE LLM, no exceptions possible

        # Memory patterns take highest priority
        if any(re.search(pattern, utterance_l) for pattern in self._USER_MEMORY_PATTERNS):
            result = "chat"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Note operations should stay in chat tool path and never map to identity.
        if any(re.search(pattern, utterance_l) for pattern in self._NOTE_PATTERNS):
            result = "chat"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Identity patterns — second priority
        if any(re.search(pattern, utterance_l) for pattern in self._IDENTITY_PATTERNS):
            result = "identity"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Greeting/smalltalk patterns — third priority
        if (
            re.search(r"^\s*(hi|hello|hey)\b", utterance_l)
            or "how are you" in utterance_l
            or re.search(r"\b(thanks|thank you)\b", utterance_l)
            or "tell me a joke" in utterance_l
        ):
            result = "chat"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Deterministic media controls
        if any(re.search(pattern, utterance_l) for pattern in self._MEDIA_PLAY_PATTERNS):
            result = "media_play"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        if any(re.search(pattern, utterance_l) for pattern in self._SCHEDULING_PATTERNS):
            result = "scheduling"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Deterministic freshness/current-events research.
        # These queries should not block on the router LLM in console certification flows.
        if any(re.search(pattern, utterance_l) for pattern in self._RESEARCH_FRESHNESS_PATTERNS):
            result = "research"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # 2. LLM handles everything else — research, system, media, ambiguous chat
        self._depth[user_key] = current + 1

        prompt = """You are the routing brain for Maya.
Given a user message, return ONLY the agent name.

AGENTS:
- identity    -> questions about Maya herself: who are you, what is your name, what can you do
- media_play  -> play music, play songs by X, put on some music, play [artist/album], spotify requests, or media control beyond basic fast-path controls
- research    -> search for, what is X, tell me about X, who made X, news about
- system      -> open file, move folder, take screenshot, close window, desktop ops
- scheduling  -> set, list, or delete reminders, alarms, or calendar events
- chat        -> greetings, small talk, follow-ups, math, jokes, and user-memory questions
                 such as "do you know my name" or "what do you know about me"

USER MESSAGE: "{utterance}"

Reply with ONLY one word: identity / media_play / research / system / scheduling / chat"""

        try:
            response = await self._llm.chat(
                prompt.format(utterance=utterance),
                max_tokens=10,
                temperature=0.0,
            )
            key = str(response or "").strip().lower().split()[0] if str(response or "").strip() else ""
            result = key if key in self.ALLOWED_KEYS else "chat"

            # Research freshness override still applies on non-protected LLM results.
            protected_intents = {"youtube", "media_play", "identity", "system"}
            if (
                result not in protected_intents
                and any(re.search(pattern, utterance_l) for pattern in self._RESEARCH_FRESHNESS_PATTERNS)
            ):
                result = "research"
        except Exception:
            result = "chat"
        finally:
            self._depth[user_key] = max(0, self._depth.get(user_key, 1) - 1)

        logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
        return result
