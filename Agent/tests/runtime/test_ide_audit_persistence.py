from __future__ import annotations

import time

import pytest

from core.ide import IDEAuditStore, PendingActionStore


@pytest.mark.asyncio
async def test_pending_actions_rehydrate_from_sqlite(tmp_path):
    db_path = tmp_path / "ide_audit.db"

    audit_store = IDEAuditStore(db_path=str(db_path))
    store = PendingActionStore(audit_store=audit_store, default_ttl_seconds=600)
    await store.start()
    created = await store.request(
        user_id="u1",
        session_id="sess-1",
        action_type="mcp:set_url",
        target_id="n8n",
        payload={"url": "http://localhost:5678"},
        risk="high",
        policy_reason="approval required",
        idempotency_key="idem-rehydrate-1",
    )
    await store.stop()

    restored_store = PendingActionStore(audit_store=audit_store, default_ttl_seconds=600)
    await restored_store.start()
    pending = await restored_store.get_pending(user_id="u1")

    assert len(pending) == 1
    assert pending[0].action_id == created.action_id
    assert pending[0].action_type == "mcp:set_url"

    await restored_store.stop()
    audit_store.close()


@pytest.mark.asyncio
async def test_expired_sqlite_actions_are_not_rehydrated(tmp_path):
    db_path = tmp_path / "ide_audit.db"

    audit_store = IDEAuditStore(db_path=str(db_path))
    audit_store.write_pending_action(
        {
            "action_id": "act_expired_1",
            "user_id": "u1",
            "session_id": "sess-1",
            "action_type": "mcp:set_url",
            "target_id": "n8n",
            "payload": {"url": "http://localhost:5678"},
            "risk": "high",
            "policy_reason": "approval required",
            "idempotency_key": "idem-expired-1",
            "requested_at": time.time() - 120,
            "expires_at": time.time() - 10,
            "trace_id": None,
            "task_id": None,
        }
    )

    store = PendingActionStore(audit_store=audit_store, default_ttl_seconds=600)
    await store.start()
    pending = await store.get_pending()

    assert pending == []

    await store.stop()
    audit_store.close()


@pytest.mark.asyncio
async def test_audit_events_write_through_to_sqlite(tmp_path):
    db_path = tmp_path / "ide_audit.db"

    audit_store = IDEAuditStore(db_path=str(db_path))
    store = PendingActionStore(audit_store=audit_store, default_ttl_seconds=600)
    await store.start()

    action = await store.request(
        user_id="u1",
        session_id="sess-1",
        action_type="mcp:set_url",
        target_id="n8n",
        payload={"url": "http://localhost:5678"},
        risk="high",
        policy_reason="approval required",
        idempotency_key="idem-audit-1",
    )
    await store.deny(
        action_id=action.action_id,
        decided_by="admin",
        reason="blocked by policy",
    )

    events = audit_store.get_audit_events(user_id="u1")
    event_types = [event["event_type"] for event in events]

    assert "requested" in event_types
    assert "denied" in event_types

    await store.stop()
    audit_store.close()
