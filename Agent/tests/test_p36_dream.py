from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.commands.handlers.dream import handle_dream
from core.features.flags import FeatureFlag, FeatureFlagSystem
from core.memory.dream import DreamCycle


@pytest.fixture
def memory_mock():
    memory = MagicMock()
    memory.retrieve_session_memories = AsyncMock(
        return_value=[{"content": f"memory entry {i}"} for i in range(8)]
    )
    memory.store = AsyncMock()
    memory.clear_session = AsyncMock(return_value=8)
    return memory


@pytest.fixture
def llm_mock():
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value="Compressed: user prefers dark mode, likes Python."
    )
    return llm


@pytest.fixture
def dream(memory_mock, llm_mock):
    return DreamCycle(memory_manager=memory_mock, llm=llm_mock)


@pytest.mark.asyncio
async def test_full_cycle_completes(dream: DreamCycle):
    result = await dream.run(session_id="sess-1", user_id="user-1")
    assert not result.skipped
    assert result.compressed_count == 8
    assert "Compressed" in result.summary_preview


@pytest.mark.asyncio
async def test_skip_below_threshold(dream: DreamCycle, memory_mock):
    memory_mock.retrieve_session_memories = AsyncMock(
        return_value=[{"content": "entry"} for _ in range(3)]
    )
    result = await dream.run(session_id="sess-2", user_id="user-1")
    assert result.skipped
    assert "3" in result.skip_reason


@pytest.mark.asyncio
async def test_long_term_store_called(dream: DreamCycle, memory_mock):
    await dream.run(session_id="sess-3", user_id="user-1")
    memory_mock.store.assert_called_once()
    kwargs = memory_mock.store.call_args.kwargs
    assert "DreamSummary" in kwargs.get("content", "")


@pytest.mark.asyncio
async def test_short_term_cleared(dream: DreamCycle, memory_mock):
    await dream.run(session_id="sess-4", user_id="user-1")
    memory_mock.clear_session.assert_called_once()


@pytest.mark.asyncio
async def test_preview_in_result(dream: DreamCycle):
    result = await dream.run(session_id="sess-5", user_id="user-1")
    assert len(result.summary_preview) <= dream.MAX_PREVIEW + 3


@pytest.mark.asyncio
async def test_compress_fallback_on_llm_error(dream: DreamCycle, llm_mock):
    llm_mock.generate = AsyncMock(side_effect=RuntimeError("LLM down"))
    result = await dream.run(session_id="sess-6", user_id="user-1")
    assert not result.skipped
    assert result.compressed_count == 8


@pytest.mark.asyncio
async def test_dream_handler_preview_and_run(dream: DreamCycle, tmp_path):
    feature_flags = FeatureFlagSystem(config_path=tmp_path / "flags.json")
    feature_flags.enable(FeatureFlag.DREAM_CYCLE)
    context = {
        "feature_flags": feature_flags,
        "dream_cycle": dream,
        "session_id": "sess-h",
        "user_id": "user-h",
    }
    preview = await handle_dream("--preview", context)
    assert "would be consolidated" in preview

    run = await handle_dream("", context)
    assert "Dream complete." in run


@pytest.mark.asyncio
async def test_dream_handler_respects_flag_off(dream: DreamCycle, tmp_path):
    feature_flags = FeatureFlagSystem(config_path=tmp_path / "flags.json")
    context = {
        "feature_flags": feature_flags,
        "dream_cycle": dream,
        "session_id": "sess-h2",
        "user_id": "user-h2",
    }
    out = await handle_dream("", context)
    assert "currently disabled" in out

