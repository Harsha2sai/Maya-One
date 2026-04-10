import pytest
from agentscope.message import Msg

from core.memory.agentscope_store import MayaAgentScopeMemory


@pytest.mark.asyncio
async def test_agentscope_store_add_and_get_recent(tmp_path):
    db_path = tmp_path / "agentscope_mem.db"
    store = MayaAgentScopeMemory(db_path=str(db_path))

    await store.add(Msg(name="user", role="user", content="hello"), persist=False, session_id="s1")
    await store.add(Msg(name="maya", role="assistant", content="hi"), persist=False, session_id="s1")

    recent = await store.get_recent(k=2, session_id="s1")
    assert len(recent) == 2
    assert str(recent[-1].content) == "hi"


@pytest.mark.asyncio
async def test_agentscope_store_persist_and_read_back(tmp_path):
    db_path = tmp_path / "agentscope_mem.db"
    store = MayaAgentScopeMemory(db_path=str(db_path))

    await store.add(Msg(name="user", role="user", content="persist me"), persist=True, session_id="s2")
    persisted = await store.get_persisted(session_id="s2", limit=5)
    assert persisted
    assert str(persisted[0].content) == "persist me"


@pytest.mark.asyncio
async def test_agentscope_store_validate_parity_for_five_sessions(tmp_path):
    db_path = tmp_path / "agentscope_mem.db"
    store = MayaAgentScopeMemory(db_path=str(db_path))

    for idx in range(1, 6):
        session_id = f"s{idx}"
        await store.add(
            Msg(name="user", role="user", content=f"msg-{idx}"),
            persist=True,
            session_id=session_id,
        )

    parity = await store.validate_parity(sample_sessions=5)
    assert parity["sample_limit"] == 5
    assert parity["sampled_sessions"] == 5
    assert parity["parity_ok"] is True
