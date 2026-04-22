"""Session-scoped action state store with bounded lifecycle and carryover helpers."""
from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional

from core.action.constants import ActionStateConfig
from core.action.models import ActionIntent, ToolReceipt


@dataclass
class _SessionState:
    recent_opened_apps: Deque[dict[str, Any]]
    recent_closed_apps: Deque[dict[str, Any]]
    recent_searches: Deque[dict[str, Any]]
    action_history: Deque[dict[str, Any]]
    last_action: Optional[Dict[str, Any]] = None
    last_action_expiry_reason: Optional[str] = None
    turn_index: int = 0
    last_touch: float = field(default_factory=time.time)


class ActionStateStore:
    def __init__(self, config: Optional[ActionStateConfig] = None) -> None:
        self.config = config or ActionStateConfig()
        self._sessions: Dict[str, _SessionState] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _session_key(self, session_id: str) -> str:
        return str(session_id or "unknown_session").strip() or "unknown_session"

    def _make_state(self) -> _SessionState:
        return _SessionState(
            recent_opened_apps=deque(maxlen=self.config.max_opened_apps),
            recent_closed_apps=deque(maxlen=self.config.max_opened_apps),
            recent_searches=deque(maxlen=self.config.max_search_queries),
            action_history=deque(maxlen=self.config.max_actions),
        )

    def _lock_for(self, session_key: str) -> asyncio.Lock:
        return self._locks.setdefault(session_key, asyncio.Lock())

    def _state_for(self, session_key: str) -> _SessionState:
        state = self._sessions.get(session_key)
        if state is None:
            state = self._make_state()
            self._sessions[session_key] = state
        return state

    def _prune_expired_locked(self, session_key: str) -> None:
        now = time.time()
        state = self._sessions.get(session_key)
        if not state:
            return

        while state.recent_searches and (now - float(state.recent_searches[0].get("ts", now))) > self.config.search_query_ttl_seconds:
            state.recent_searches.popleft()
        while state.action_history and (now - float(state.action_history[0].get("ts", now))) > self.config.default_ttl_seconds:
            state.action_history.popleft()
        while state.recent_opened_apps and (now - float(state.recent_opened_apps[0].get("ts", now))) > self.config.default_ttl_seconds:
            state.recent_opened_apps.popleft()
        while state.recent_closed_apps and (now - float(state.recent_closed_apps[0].get("ts", now))) > self.config.default_ttl_seconds:
            state.recent_closed_apps.popleft()

        if state.last_action is not None:
            _action, reason = self._resolve_last_action_locked(state, now=now)
            if reason in {"expired_ttl", "expired_turns"}:
                state.last_action_expiry_reason = reason

        if now - float(state.last_touch or now) > self.config.search_query_ttl_seconds and not (
            state.recent_opened_apps
            or state.recent_closed_apps
            or state.recent_searches
            or state.action_history
            or state.last_action is not None
            or state.last_action_expiry_reason is not None
        ):
            self._sessions.pop(session_key, None)
            self._locks.pop(session_key, None)

    def _resolve_last_action_locked(
        self,
        state: _SessionState,
        *,
        now: Optional[float] = None,
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        if state.last_action is None:
            return None, "no_state"
        if not isinstance(state.last_action, dict):
            state.last_action = None
            return None, "no_state"

        now_ts = float(now if now is not None else time.time())
        written_at_ts = float(
            state.last_action.get("written_at_ts")
            or state.last_action.get("ts")
            or 0.0
        )
        if written_at_ts > 0 and (now_ts - written_at_ts) > float(self.config.last_action_ttl_seconds):
            state.last_action = None
            return None, "expired_ttl"

        written_turn = int(
            state.last_action.get("written_at_turn")
            or state.last_action.get("turn_index")
            or 0
        )
        if (state.turn_index - written_turn) > int(self.config.last_action_max_turns):
            state.last_action = None
            return None, "expired_turns"

        return dict(state.last_action), None

    def increment_turn(self, session_id: str) -> int:
        session_key = self._session_key(session_id)
        state = self._state_for(session_key)
        state.turn_index += 1
        state.last_touch = time.time()
        self._prune_expired_locked(session_key)
        return state.turn_index

    def current_turn(self, session_id: str) -> int:
        session_key = self._session_key(session_id)
        state = self._state_for(session_key)
        return int(state.turn_index)

    def set_last_action(self, session_id: str, action: Dict[str, Any]) -> None:
        session_key = self._session_key(session_id)
        state = self._state_for(session_key)
        now = time.time()
        payload = dict(action or {})
        payload.setdefault("written_at_ts", now)
        payload.setdefault("written_at_turn", state.turn_index)
        state.last_action = payload
        state.last_action_expiry_reason = None
        state.last_touch = now
        self._prune_expired_locked(session_key)

    def get_last_action(self, session_id: str) -> Optional[Dict[str, Any]]:
        action, _reason = self.get_last_action_with_reason(session_id)
        return action

    def get_last_action_with_reason(self, session_id: str) -> tuple[Optional[Dict[str, Any]], str]:
        session_key = self._session_key(session_id)
        state = self._sessions.get(session_key)
        if state is None:
            return None, "no_state"
        if state.last_action is None and state.last_action_expiry_reason:
            reason = str(state.last_action_expiry_reason)
            state.last_action_expiry_reason = None
            self._prune_expired_locked(session_key)
            return None, reason
        action, reason = self._resolve_last_action_locked(state, now=time.time())
        self._prune_expired_locked(session_key)
        if action is None:
            return None, str(reason or "no_state")
        return action, "active"

    def clear_last_action(self, session_id: str) -> None:
        session_key = self._session_key(session_id)
        state = self._sessions.get(session_key)
        if state is None:
            return
        state.last_action = None
        state.last_action_expiry_reason = None
        state.last_touch = time.time()
        self._prune_expired_locked(session_key)

    async def record_intent(self, session_id: str, intent: ActionIntent) -> None:
        session_key = self._session_key(session_id)
        lock = self._lock_for(session_key)
        async with lock:
            state = self._state_for(session_key)
            now = time.time()
            state.last_touch = now
            state.action_history.append(
                {
                    "type": "intent",
                    "operation": intent.operation,
                    "target": intent.target,
                    "query": intent.query,
                    "ts": now,
                }
            )
            self._prune_expired_locked(session_key)

    async def mark_turn_start(self, session_id: str, turn_id: str, message: str) -> None:
        session_key = self._session_key(session_id)
        lock = self._lock_for(session_key)
        async with lock:
            state = self._state_for(session_key)
            now = time.time()
            state.last_touch = now
            state.action_history.append(
                {
                    "type": "turn_start",
                    "turn_id": str(turn_id or ""),
                    "message": str(message or "")[:200],
                    "ts": now,
                }
            )
            self._prune_expired_locked(session_key)

    async def mark_turn_end(self, session_id: str, turn_id: str, route: str) -> None:
        session_key = self._session_key(session_id)
        lock = self._lock_for(session_key)
        async with lock:
            state = self._state_for(session_key)
            now = time.time()
            state.last_touch = now
            state.action_history.append(
                {
                    "type": "turn_end",
                    "turn_id": str(turn_id or ""),
                    "route": str(route or ""),
                    "ts": now,
                }
            )
            self._prune_expired_locked(session_key)

    async def record_receipt(self, session_id: str, receipt: ToolReceipt) -> None:
        session_key = self._session_key(session_id)
        lock = self._lock_for(session_key)
        async with lock:
            state = self._state_for(session_key)
            now = time.time()
            state.last_touch = now
            state.action_history.append(
                {
                    "type": "receipt",
                    "operation": receipt.tool_name,
                    "status": receipt.status,
                    "success": receipt.success,
                    "message": receipt.message,
                    "ts": now,
                }
            )
            if receipt.success:
                self._update_successful_action_locked(state, receipt, now)
            self._prune_expired_locked(session_key)

    def _update_successful_action_locked(self, state: _SessionState, receipt: ToolReceipt, now: float) -> None:
        tool_name = str(receipt.tool_name or "").strip().lower()
        normalized = receipt.normalized_result or {}
        if tool_name == "open_app":
            app_name = str(normalized.get("app_name") or normalized.get("target") or "").strip()
            if app_name:
                state.recent_opened_apps.append({"app": app_name, "ts": now})
        elif tool_name == "close_app":
            app_name = str(normalized.get("app_name") or normalized.get("target") or "").strip()
            if app_name:
                state.recent_closed_apps.append({"app": app_name, "ts": now})
        elif tool_name == "web_search":
            query = self._extract_search_query(normalized)
            if query:
                state.recent_searches.append({"query": query, "subject": query, "ts": now})

    @staticmethod
    def _extract_search_query(payload: Dict[str, Any]) -> str:
        query = str(payload.get("query") or "").strip()
        if query:
            return query
        app_name = str(payload.get("app_name") or "").strip().lower()
        marker = "youtube search for "
        if app_name.startswith(marker):
            return app_name[len(marker):].strip()
        return ""

    async def set_active_subject(self, session_id: str, subject: str, query: str = "") -> None:
        session_key = self._session_key(session_id)
        lock = self._lock_for(session_key)
        async with lock:
            state = self._state_for(session_key)
            now = time.time()
            state.last_touch = now
            clean_subject = str(subject or "").strip()
            clean_query = str(query or clean_subject).strip()
            if clean_subject or clean_query:
                state.recent_searches.append(
                    {"subject": clean_subject, "query": clean_query, "ts": now}
                )
            self._prune_expired_locked(session_key)

    async def resolve_pronoun(self, session_id: str, token: str) -> str:
        del token
        session_key = self._session_key(session_id)
        lock = self._lock_for(session_key)
        async with lock:
            state = self._state_for(session_key)
            self._prune_expired_locked(session_key)
            for entry in reversed(state.recent_searches):
                subject = str(entry.get("subject") or entry.get("query") or "").strip()
                if subject:
                    return subject
            return ""

    def resolve_pronoun_sync(self, session_id: str, token: str) -> str:
        del token
        session_key = self._session_key(session_id)
        state = self._sessions.get(session_key)
        if not state:
            return ""
        self._prune_expired_locked(session_key)
        state = self._sessions.get(session_key)
        if not state:
            return ""
        for entry in reversed(state.recent_searches):
            subject = str(entry.get("subject") or entry.get("query") or "").strip()
            if subject:
                return subject
        return ""

    async def resolve_additive(self, session_id: str, utterance: str) -> str:
        text = str(utterance or "").strip().lower()
        if not text.startswith("also "):
            return ""
        session_key = self._session_key(session_id)
        lock = self._lock_for(session_key)
        async with lock:
            state = self._state_for(session_key)
            self._prune_expired_locked(session_key)
            addon = text.replace("also", "", 1).strip()
            if not addon:
                return ""
            for entry in reversed(state.recent_opened_apps):
                app = str(entry.get("app") or "").strip()
                if app:
                    return f"{app} and {addon}"
            return addon

    async def resolve_continuation(self, session_id: str, utterance: str) -> str:
        text = str(utterance or "").strip().lower()
        if not text:
            return ""
        continuation_hit = bool(
            re.search(r"\b(about it|search more|more about it|videos about it)\b", text)
            or text in {"it", "that", "this", "them"}
        )
        if not continuation_hit:
            return ""
        return await self.resolve_pronoun(session_id, "it")

    def resolve_continuation_sync(self, session_id: str, utterance: str) -> str:
        text = str(utterance or "").strip().lower()
        if not text:
            return ""
        continuation_hit = bool(
            re.search(r"\b(about it|search more|more about it|videos about it)\b", text)
            or text in {"it", "that", "this", "them"}
        )
        if not continuation_hit:
            return ""
        return self.resolve_pronoun_sync(session_id, "it")

    def latest_opened_app_sync(self, session_id: str) -> str:
        session_key = self._session_key(session_id)
        state = self._sessions.get(session_key)
        if not state:
            return ""
        self._prune_expired_locked(session_key)
        state = self._sessions.get(session_key)
        if not state or not state.recent_opened_apps:
            return ""
        latest = state.recent_opened_apps[-1]
        return str(latest.get("app") or "").strip()
