import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_CLASSIFIER_PROMPT = """\
You are a routing classifier. Reply with exactly one word: "fact" or "research".

"fact" = single deterministic answer (a name, number, place, date). No explanation needed.
"research" = requires explanation, current events, recent data, opinions, or multi-sentence answer.

Examples:
who is the prime minister of india -> fact
भारत का प्रधानमंत्री कौन है -> fact
quien es el presidente de mexico -> fact
yaar who is the PM bata -> fact
what is the capital of France -> fact
how old is Elon Musk -> fact
what is retrieval augmented generation -> research
who made Linux -> research
latest news about AI -> research
how does photosynthesis work -> research
explain quantum computing -> research

Question: {message}
Answer:"""


class FactClassifier:
    """
    Determines whether a message is a simple single-fact query
    or requires research. Uses the router LLM directly so it
    works for any language or code-mixed input.

    Only fires when base_route == "research". All other routes
    bypass this entirely.
    """

    def __init__(self, llm_client: Any):
        self._llm = llm_client
        self._cache: dict[str, bool] = {}

    async def is_simple_fact(self, message: str) -> bool:
        key = message.lower().strip()
        if key in self._cache:
            return self._cache[key]

        heuristic = self._heuristic_fact_check(key)
        if heuristic is not None:
            self._cache[key] = heuristic
            return heuristic

        try:
            prompt = _CLASSIFIER_PROMPT.format(message=message)
            response = await self._llm.chat(prompt, max_tokens=5, temperature=0.0)
            is_fact = response.strip().lower().startswith("fact")
            self._cache[key] = is_fact
            logger.info(
                "fact_classifier message=%r result=%s",
                message[:60],
                "fact" if is_fact else "research",
            )
            return is_fact
        except Exception as e:
            logger.warning("fact_classifier_failed error=%s — defaulting to research", e)
            self._cache[key] = False
            return False

    @staticmethod
    def _heuristic_fact_check(message_l: str) -> bool | None:
        freshness_terms = (
            " current ",
            " present ",
            " latest ",
            " recent ",
            " today ",
            " right now",
            " this week",
            " new ",
        )
        normalized = f" {message_l.strip()} "
        if any(term in normalized for term in freshness_terms):
            return False

        research_exclusions = (
            "retrieval augmented generation",
            "who made ",
            "how does ",
            "explain ",
            "latest news",
        )
        if any(token in message_l for token in research_exclusions):
            return False

        fact_patterns = (
            r"\bwho is (?:the )?(?:pm|prime minister|president|vice president|ceo|cto|cfo|founder|director|governor)\s+of\b",
            r"\bwho runs\b",
            r"\bwho founded\b",
            r"\bwhat is\b",
            r"\bhow old is\b",
            r"\bhow tall is\b",
        )
        if any(re.search(pattern, message_l) for pattern in fact_patterns):
            return True

        return None
