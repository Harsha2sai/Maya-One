
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Expanded stopwords list to catch common conversational noise
FTS_STOPWORDS = {
    "hi", "hello", "hey", "ok", "thanks", "thank", "you", "yes", "no", 
    "hmm", "test", "testing", "please", "can", "will", "do", "what", "how"
}
FTS_RESERVED_OPERATORS = {"and", "or", "not", "near"}

def sanitize_fts_query(query: str) -> Optional[str]:
    """
    Sanitize and quote an FTS query to avoid syntax errors with special tokens.
    """
    if not query:
        return None

    # Keep only word-like tokens so operators/symbols don't break MATCH parsing.
    tokens = re.findall(r"[A-Za-z0-9_]+", query)
    if not tokens:
        return None

    filtered_tokens = []
    for token in tokens:
        lowered = token.lower()
        if lowered in FTS_STOPWORDS or lowered in FTS_RESERVED_OPERATORS:
            continue
        filtered_tokens.append(token)

    if not filtered_tokens:
        logger.debug(f"FTS Query '{query}' sanitized to empty (all stopwords/noise).")
        return None

    has_robust_word = any(len(token) >= 3 for token in filtered_tokens)
    if not has_robust_word:
        logger.debug(f"FTS Query '{query}' rejected: No word >= 3 chars.")
        return None

    # Regex-tokenized terms are already safe for FTS MATCH.
    # Keep plain terms to preserve existing query semantics/tests.
    unique_tokens = []
    seen = set()
    for token in filtered_tokens:
        if token in seen:
            continue
        seen.add(token)
        unique_tokens.append(token)

    final_query = " OR ".join(unique_tokens[:12])
    return final_query
