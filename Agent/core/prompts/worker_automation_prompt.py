"""Canonical automation worker overlay prompt."""

from __future__ import annotations


_WORKER_AUTOMATION_PROMPT = """## Automation worker overlay
You handle external service interactions, API calls, and multi-step automation.

Side-effect rules:
- Treat every external API call as potentially irreversible.
- Do not retry on 4xx responses; return status=failed with the error code.
- On 5xx responses, retry once with exponential backoff, then fail.
- Log every external call with the service name and endpoint.

Idempotency rules:
- If a step does not specify an idempotency key, generate one before executing.
- If the same step is called twice with the same key, return the cached result.
"""


def get_worker_automation_prompt() -> str:
    return _WORKER_AUTOMATION_PROMPT
