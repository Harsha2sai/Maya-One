import pytest
from types import SimpleNamespace

from core.orchestrator.memory_context_service import MemoryContextService
from core.telemetry.runtime_metrics import RuntimeMetrics


class _StubLLM:
    def __init__(self, outputs: dict[str, str]):
        self.outputs = outputs

    async def chat(self, prompt: str, max_tokens: int = 5, temperature: float = 0.0) -> str:
        del max_tokens, temperature
        prompt_l = prompt.lower()
        for key, value in self.outputs.items():
            if key in prompt_l:
                return value
        return "general"


class _StubMemory:
    def __init__(self, responses: dict[str, list[dict]]):
        self._responses = responses

    async def retrieve_relevant_memories_with_scope_fallback_async(
        self,
        query: str,
        **_kwargs,
    ) -> list[dict]:
        return list(self._responses.get(query, []))


def _owner(memory: _StubMemory, llm: _StubLLM):
    return SimpleNamespace(
        memory=memory,
        _router_llm_adapter=llm,
        _memory_disabled_until=0.0,
        _memory_timeout_count=0,
        _is_name_query=lambda text: "your name" in str(text).lower(),
        _is_creator_query=lambda text: "who made you" in str(text).lower(),
        _should_skip_memory=lambda text, origin, mode: (True, "skip_gate"),
        _is_tool_focused_query=lambda text: "what is" in str(text).lower(),
        _format_memory_context=lambda memories: "\n".join(f"- {m.get('text', '')}" for m in memories),
    )


@pytest.mark.asyncio
async def test_classify_memory_query_type_uses_llm_and_hard_identity_negative():
    service = MemoryContextService(
        owner=_owner(
            memory=_StubMemory({}),
            llm=_StubLLM(
                {
                    "what is my name": "profile",
                    "what is my name in python": "general",
                }
            ),
        )
    )

    assert (
        await service.classify_memory_query_type_async(
            "what is my name",
            route_hint="chat",
            session_id="s1",
        )
        == "user_profile_recall"
    )
    assert (
        await service.classify_memory_query_type_async(
            "what is your name",
            route_hint="identity",
            session_id="s1",
        )
        == "general"
    )
    assert (
        await service.classify_memory_query_type_async(
            "what is my name in python",
            route_hint="chat",
            session_id="s1",
        )
        == "general"
    )


@pytest.mark.asyncio
async def test_resolve_profile_recall_prefers_profile_over_vector_conflict():
    RuntimeMetrics.reset()
    service = MemoryContextService(
        owner=_owner(
            memory=_StubMemory(
                {
                    "User profile fact: name=": [
                        {
                            "text": "User profile fact: name=Harsha",
                            "metadata": {
                                "memory_kind": "profile_fact",
                                "field": "name",
                                "value": "Harsha",
                            },
                        }
                    ],
                    "what is my name": [
                        {"text": "User: my name is Harsha Reddy"},
                    ],
                }
            ),
            llm=_StubLLM({}),
        )
    )

    value, source, miss_reason = await service.resolve_profile_recall(
        "what is my name",
        user_id="u1",
        session_id="s1",
        origin="chat",
    )

    assert value == "Harsha"
    assert source == "profile"
    assert miss_reason == ""


@pytest.mark.asyncio
async def test_profile_recall_bypasses_skip_and_tool_focused_gate():
    RuntimeMetrics.reset()
    memory = _StubMemory(
        {
            "what is my name": [
                {
                    "text": "User: my name is Harsha",
                    "metadata": {"created_at": "2026-04-22T12:00:00+00:00"},
                }
            ]
        }
    )
    service = MemoryContextService(owner=_owner(memory=memory, llm=_StubLLM({})))

    memory_context = await service.retrieve_memory_context_async(
        "what is my name",
        origin="chat",
        routing_mode_type="informational",
        user_id="u1",
        session_id="s1",
        query_type="user_profile_recall",
    )

    assert "my name is Harsha" in memory_context
