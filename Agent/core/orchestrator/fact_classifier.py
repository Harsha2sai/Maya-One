import logging
from typing import Any

logger = logging.getLogger(__name__)

_CLASSIFIER_PROMPT = """\
You are a routing classifier. Decide if a question needs web research or can be answered from general knowledge.

Reply with exactly one word: fact OR research

fact = single deterministic answer (a name, number, place, date) that does not need web search
research = requires explanation, current events, recent data, opinions, or multi-sentence answer

Examples:
who is the prime minister of india -> fact
भारत का प्रधानमंत्री कौन है -> fact
quien es el presidente de mexico -> fact
yaar who is the PM bata -> fact
who is the ceo of google -> fact
what is the capital of france -> fact
how old is elon musk -> fact
what is retrieval augmented generation -> research
who made linux -> research
latest news about AI -> research
how does photosynthesis work -> research
explain quantum computing -> research
what are the benefits of meditation -> research

Question: {message}
Answer:"""


class FactClassifier:
    """
    LLM-based simple-fact detector.
    Works for any language or code-mixed input.
    Only fires when the base route is already 'research'.
    Session-level cache avoids redundant calls for repeated queries.
    """

    def __init__(self, llm_client: Any):
        self._llm = llm_client
        self._cache: dict[str, bool] = {}

    async def is_simple_fact(self, message: str) -> bool:
        key = message.lower().strip()
        if key in self._cache:
            return self._cache[key]

        try:
            prompt = _CLASSIFIER_PROMPT.format(message=message)
            response = await self._llm.chat(
                prompt=prompt,
                max_tokens=5,
                temperature=0.0,
            )
            is_fact = response.strip().lower().startswith("fact")
            self._cache[key] = is_fact
            logger.debug(
                "fact_classifier result=%s message=%r",
                "fact" if is_fact else "research",
                message[:60],
            )
            return is_fact
        except Exception as exc:
            logger.debug("fact_classifier_failed error=%s — defaulting to research", exc)
            self._cache[key] = False
            return False
