"""Deterministic cross-state arbitration for turn ownership."""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.telemetry.runtime_metrics import RuntimeMetrics

logger = logging.getLogger(__name__)


@dataclass
class ArbitrationDecision:
    owner: str
    confidence: float
    reason: str
    scores: Dict[str, float] = field(default_factory=dict)
    clarify_reason: str = ""
    clarify_message: str = ""
    explicit_intent: str = ""
    query_type: str = "general"


class StateArbiter:
    """Single per-turn owner selector across entity/action/profile/chat domains."""

    _PROFILE_SELF_PATTERNS = (
        r"\bwhat(?:'s| is)\s+my\s+name\b",
        r"\bwho\s+am\s+i\b",
        r"\bremember\s+my\b",
        r"\bdo\s+you\s+remember\s+me\b",
        r"\bdo\s+you\s+know\s+my\s+name\b",
        r"\bwhat\s+do\s+you\s+know\s+about\s+me\b",
    )
    _IDENTITY_SELF_PATTERNS = (
        r"\bwhat(?:'s| is)\s+your\s+name\b",
        r"\bwho\s+are\s+you\b",
        r"\btell\s+me\s+about\s+yourself\b",
    )
    _SYSTEM_PATTERNS = (
        r"\bopen\s+(?:the\s+)?(?:app|application|browser|folder|file|settings|terminal)\b",
        r"\bclose\s+(?:the\s+)?(?:app|application|window|browser)\b",
        r"\bclick\b",
        r"\btype\b",
        r"\btake\s+(?:a\s+)?screenshot\b",
    )
    _SCHEDULING_PATTERNS = (
        r"\bremind me\b",
        r"\bset\s+(?:a\s+)?reminder\b",
        r"\bset\s+(?:an\s+)?alarm\b",
        r"\blist reminders\b",
        r"\bshow reminders\b",
        r"\bdelete reminder\b",
        r"\bwhat reminder did\b",
        r"\bwhen is (?:my|the) reminder\b",
    )
    _REMINDER_FOLLOWUP_HINTS = (
        r"\breminder\b",
        r"\balarm\b",
        r"\bwhat did you set\b",
        r"\bwhen is it\b",
        r"\bwhat(?:'s| is)\s+it\s+for\b",
        r"\bwhich reminder\b",
    )
    _FOLLOWUP_HINTS = (
        r"\btell me more\b",
        r"\bmore about\b",
        r"\bwhat about\b",
        r"\babout him\b",
        r"\babout her\b",
        r"\babout them\b",
        r"\babout it\b",
    )

    def __init__(self, *, owner: Any):
        self._owner = owner
        self._shadow = self._truthy_env("STATE_ARBITER_SHADOW", True)
        self._enforce = self._truthy_env("STATE_ARBITER_ENFORCE", False)
        self._ambiguity_delta = self._float_env("STATE_ARBITER_AMBIGUITY_DELTA", 0.15)
        self._min_confidence = self._float_env("STATE_ARBITER_MIN_CONFIDENCE", 0.60)
        self._clarify_fallback_conf = self._float_env("STATE_ARBITER_CLARIFY_FALLBACK_CONF", 0.70)
        self._clarify_memory_turns = max(1, self._int_env("STATE_ARBITER_CLARIFY_MEMORY_TURNS", 2))
        self._clarify_max_generic_attempts = max(
            1,
            self._int_env("STATE_ARBITER_CLARIFY_MAX_GENERIC_ATTEMPTS", 1),
        )
        self._clarify_context: Dict[str, Dict[str, Any]] = {}

    @property
    def shadow_enabled(self) -> bool:
        return self._shadow

    @property
    def enforce_enabled(self) -> bool:
        return self._enforce

    async def arbitrate_turn(
        self,
        *,
        message: str,
        origin: str = "chat",
        tool_context: Any = None,
        user_id: str = "",
    ) -> ArbitrationDecision:
        text = re.sub(r"\s+", " ", str(message or "")).strip()
        lowered = text.lower()
        session_key = self._owner._session_key_for_context(tool_context)
        turn_index = int(self._owner._current_action_state_turn(tool_context))
        state = self._clean_state(tool_context=tool_context, session_key=session_key)

        explicit_intent = self._classify_explicit_intent(lowered)
        if explicit_intent:
            decision = self._decision_from_explicit_intent(explicit_intent)
            RuntimeMetrics.increment("state_arbiter_decision_total")
            logger.info(
                "state_arbiter_decision owner=%s confidence=%.2f reason=%s explicit_intent=%s session=%s",
                decision.owner,
                decision.confidence,
                decision.reason,
                explicit_intent,
                session_key,
            )
            self._clear_clarify_context(session_key)
            return decision

        clarify_ctx = self._get_clarify_context(session_key=session_key, turn_index=turn_index)

        query_type = "general"
        if self._is_profile_self_reference(lowered):
            query_type = await self._owner._classify_memory_query_type_async(
                text,
                route_hint="chat",
                session_id=session_key,
            )

        scores = self._score_candidates(
            text=lowered,
            state=state,
            query_type=query_type,
            clarify_ctx=clarify_ctx,
        )
        winner, second = self._top_two(scores)
        winner_owner, winner_score = winner
        second_owner, second_score = second

        if self._is_profile_self_reference(lowered) and winner_owner != "profile_recall":
            profile_score = max(
                scores.get("profile_recall", 0.0),
                min(1.0, scores.get("entity_followup", 0.0) + 0.2),
                0.75,
            )
            scores["profile_recall"] = profile_score
            winner, second = self._top_two(scores)
            winner_owner, winner_score = winner
            second_owner, second_score = second

        ambiguous = self._is_ambiguous_pair(
            winner_owner=winner_owner,
            winner_score=winner_score,
            second_owner=second_owner,
            second_score=second_score,
        )

        if ambiguous or winner_score < self._min_confidence:
            decision = self._build_clarify_or_fallback(
                session_key=session_key,
                turn_index=turn_index,
                winner_owner=winner_owner,
                winner_score=winner_score,
                second_owner=second_owner,
                second_score=second_score,
                query_type=query_type,
                scores=scores,
                ambiguous=ambiguous,
            )
            RuntimeMetrics.increment("state_arbiter_decision_total")
            RuntimeMetrics.increment("state_arbiter_ambiguity_total")
            RuntimeMetrics.increment("state_arbiter_clarify_total")
            logger.info(
                "state_arbiter_decision owner=%s confidence=%.2f reason=%s clarify_reason=%s scores=%s session=%s",
                decision.owner,
                decision.confidence,
                decision.reason,
                decision.clarify_reason,
                self._short_scores(scores),
                session_key,
            )
            return decision

        self._clear_clarify_context(session_key)
        decision = ArbitrationDecision(
            owner=winner_owner,
            confidence=winner_score,
            reason=f"deterministic_score winner={winner_owner} second={second_owner}",
            scores=scores,
            query_type=query_type,
        )
        RuntimeMetrics.increment("state_arbiter_decision_total")
        logger.info(
            "state_arbiter_decision owner=%s confidence=%.2f reason=%s scores=%s session=%s",
            decision.owner,
            decision.confidence,
            decision.reason,
            self._short_scores(scores),
            session_key,
        )
        return decision

    def record_outcome(
        self,
        *,
        decision: Optional[ArbitrationDecision],
        legacy_owner: str,
        final_handler: str = "",
    ) -> None:
        if decision is None:
            return
        legacy = str(legacy_owner or "").strip().lower()
        final = str(final_handler or legacy_owner or "").strip().lower()
        chosen = str(decision.owner or "").strip().lower()
        if not legacy:
            return
        if self._shadow and chosen and chosen != legacy:
            RuntimeMetrics.increment("state_arbiter_outcome_mismatch_total")
            logger.info(
                "state_arbiter_shadow_mismatch chosen=%s legacy=%s final=%s reason=%s",
                chosen,
                legacy,
                final,
                decision.reason,
            )
            return
        if self._enforce and chosen and final and chosen != final:
            RuntimeMetrics.increment("state_arbiter_outcome_mismatch_total")
            logger.info(
                "state_arbiter_enforce_mismatch chosen=%s final=%s reason=%s",
                chosen,
                final,
                decision.reason,
            )

    def _clean_state(self, *, tool_context: Any, session_key: str) -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "active_entity": None,
            "last_action": None,
            "pending_scheduling_action": None,
            "recent_research": False,
        }
        store = getattr(self._owner, "_action_state_store", None)
        if store is not None:
            session_state = getattr(store, "_sessions", {}).get(session_key)
            now_ts = time.time()
            if session_state is not None:
                # Read-only sanitation: do not consume expiry reasons from the main store.
                active_status = store._active_entity_status_locked(session_state, now=now_ts)
                if active_status is None and isinstance(session_state.active_entity, dict):
                    state["active_entity"] = dict(session_state.active_entity)
                elif active_status in {"expired_ttl", "expired_turns", "drifted_context"}:
                    logger.info(
                        "state_arbiter_state_sanitized state=active_entity reason=%s session=%s",
                        active_status,
                        session_key,
                    )

                last_reason = None
                if isinstance(session_state.last_action, dict):
                    written_at_ts = float(
                        session_state.last_action.get("written_at_ts")
                        or session_state.last_action.get("ts")
                        or 0.0
                    )
                    if written_at_ts > 0 and (now_ts - written_at_ts) > float(store.config.last_action_ttl_seconds):
                        last_reason = "expired_ttl"
                    else:
                        written_turn = int(
                            session_state.last_action.get("written_at_turn")
                            or session_state.last_action.get("turn_index")
                            or 0
                        )
                        if (int(session_state.turn_index) - written_turn) > int(store.config.last_action_max_turns):
                            last_reason = "expired_turns"
                if last_reason is None and isinstance(session_state.last_action, dict):
                    state["last_action"] = dict(session_state.last_action)
                elif last_reason in {"expired_ttl", "expired_turns"}:
                    logger.info(
                        "state_arbiter_state_sanitized state=last_action reason=%s session=%s",
                        last_reason,
                        session_key,
                    )

                pending_status = store._pending_scheduling_status_locked(session_state, now=now_ts)
                if pending_status is None and isinstance(session_state.pending_scheduling_action, dict):
                    state["pending_scheduling_action"] = dict(session_state.pending_scheduling_action)
                elif pending_status in {"expired_ttl", "expired_turns"}:
                    logger.info(
                        "state_arbiter_state_sanitized state=pending_scheduling_action reason=%s session=%s",
                        pending_status,
                        session_key,
                    )

        history = list(getattr(self._owner, "_conversation_history", []) or [])
        for item in reversed(history[-6:]):
            if not isinstance(item, dict):
                continue
            if str(item.get("route") or "").strip().lower() == "research":
                state["recent_research"] = True
                break
        return state

    def _classify_explicit_intent(self, lowered: str) -> str:
        if any(re.search(pattern, lowered) for pattern in self._IDENTITY_SELF_PATTERNS):
            return "identity_self"
        if any(re.search(pattern, lowered) for pattern in self._PROFILE_SELF_PATTERNS):
            if re.search(r"\b(python|javascript|java|function|class|variable|code)\b", lowered):
                return ""
            return "profile_self_reference"
        if any(re.search(pattern, lowered) for pattern in self._SCHEDULING_PATTERNS):
            return "scheduling_command"
        if any(re.search(pattern, lowered) for pattern in self._SYSTEM_PATTERNS):
            return "system_command"
        return ""

    @staticmethod
    def _decision_from_explicit_intent(explicit_intent: str) -> ArbitrationDecision:
        mapping = {
            "identity_self": ("identity", 0.98, "explicit_intent_identity"),
            "profile_self_reference": ("profile_recall", 0.95, "explicit_intent_profile"),
            "scheduling_command": ("scheduling_command", 0.95, "explicit_intent_scheduling"),
            "system_command": ("system_command", 0.95, "explicit_intent_system"),
        }
        owner, confidence, reason = mapping.get(
            explicit_intent,
            ("general_chat", 0.60, "explicit_intent_fallback"),
        )
        return ArbitrationDecision(
            owner=owner,
            confidence=confidence,
            reason=reason,
            explicit_intent=explicit_intent,
            scores={owner: confidence},
        )

    def _score_candidates(
        self,
        *,
        text: str,
        state: Dict[str, Any],
        query_type: str,
        clarify_ctx: Optional[Dict[str, Any]],
    ) -> Dict[str, float]:
        scores: Dict[str, float] = {
            "entity_followup": 0.0,
            "action_followup": 0.0,
            "profile_recall": 0.0,
            "general_memory": 0.0,
            "general_chat": 0.35,
        }

        pronoun = bool(getattr(self._owner, "_pronoun_rewriter", None) and self._owner._pronoun_rewriter.has_pronoun(text))
        followup_hint = any(re.search(pattern, text) for pattern in self._FOLLOWUP_HINTS)
        reminder_hint = any(re.search(pattern, text) for pattern in self._REMINDER_FOLLOWUP_HINTS)
        self_ref = self._is_profile_self_reference(text)
        short_query = len(re.findall(r"\b[\w'-]+\b", text)) <= 10

        has_active_entity = isinstance(state.get("active_entity"), dict) and bool(
            str((state.get("active_entity") or {}).get("value") or "").strip()
        )
        has_last_action = isinstance(state.get("last_action"), dict) and str(
            (state.get("last_action") or {}).get("domain") or ""
        ).strip().lower() == "scheduling"
        has_pending_scheduling = isinstance(state.get("pending_scheduling_action"), dict)
        recent_research = bool(state.get("recent_research"))

        if pronoun:
            scores["entity_followup"] += 0.4
        if has_active_entity:
            scores["entity_followup"] += 0.3
        if recent_research:
            scores["entity_followup"] += 0.2
        if followup_hint:
            scores["entity_followup"] += 0.1

        if reminder_hint:
            scores["action_followup"] += 0.5
        if has_last_action:
            scores["action_followup"] += 0.3
        if has_pending_scheduling:
            scores["action_followup"] += 0.2
        if short_query:
            scores["action_followup"] += 0.1
        if pronoun and has_active_entity and has_last_action and re.search(r"\bwhat about\b", text):
            # Deliberately treat this phrase as cross-domain ambiguous.
            scores["action_followup"] += 0.5

        if self_ref:
            scores["profile_recall"] += 0.5
        if str(query_type or "").strip().lower() == "user_profile_recall":
            scores["profile_recall"] += 0.3
        if not pronoun and not reminder_hint:
            scores["profile_recall"] += 0.2

        if getattr(self._owner, "_is_memory_relevant", None) and self._owner._is_memory_relevant(text):
            scores["general_memory"] += 0.4
        if re.search(r"\bremember\b", text):
            scores["general_memory"] += 0.2
        if not any(scores[key] >= 0.6 for key in ("entity_followup", "action_followup", "profile_recall")):
            scores["general_chat"] += 0.15

        if clarify_ctx:
            # One-turn disambiguation bias.
            if reminder_hint:
                scores["action_followup"] += 0.25
            if self_ref:
                scores["profile_recall"] += 0.25
            if pronoun:
                scores["entity_followup"] += 0.20

        for key, value in list(scores.items()):
            scores[key] = max(0.0, min(1.0, round(float(value), 4)))
        return scores

    @staticmethod
    def _is_profile_self_reference(text: str) -> bool:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return False
        if re.search(r"\b(python|javascript|java|function|class|variable|code)\b", lowered):
            return False
        return any(re.search(pattern, lowered) for pattern in StateArbiter._PROFILE_SELF_PATTERNS)

    @staticmethod
    def _top_two(scores: Dict[str, float]) -> tuple[tuple[str, float], tuple[str, float]]:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ordered:
            return ("general_chat", 0.0), ("general_chat", 0.0)
        if len(ordered) == 1:
            return ordered[0], ("general_chat", 0.0)
        return ordered[0], ordered[1]

    def _is_ambiguous_pair(
        self,
        *,
        winner_owner: str,
        winner_score: float,
        second_owner: str,
        second_score: float,
    ) -> bool:
        if not winner_owner or not second_owner:
            return False
        if winner_owner == second_owner:
            return False
        if (winner_score - second_score) >= self._ambiguity_delta:
            return False
        if self._owner_domain(winner_owner) == self._owner_domain(second_owner):
            return False
        if winner_owner == "general_chat" or second_owner == "general_chat":
            return False
        return True

    def _build_clarify_or_fallback(
        self,
        *,
        session_key: str,
        turn_index: int,
        winner_owner: str,
        winner_score: float,
        second_owner: str,
        second_score: float,
        query_type: str,
        scores: Dict[str, float],
        ambiguous: bool,
    ) -> ArbitrationDecision:
        clarify_reason = "low_confidence"
        if ambiguous:
            clarify_reason = self._clarify_reason_from_owners(winner_owner, second_owner)

        existing = self._get_clarify_context(session_key=session_key, turn_index=turn_index)
        if existing and int(existing.get("attempt_count") or 0) >= self._clarify_max_generic_attempts:
            if winner_score >= self._clarify_fallback_conf:
                self._clear_clarify_context(session_key)
                return ArbitrationDecision(
                    owner=winner_owner,
                    confidence=winner_score,
                    reason="clarify_loop_fallback_best_owner",
                    scores=scores,
                    query_type=query_type,
                )
            return ArbitrationDecision(
                owner="clarify",
                confidence=max(winner_score, second_score),
                reason="clarify_loop_hard_prompt",
                scores=scores,
                query_type=query_type,
                clarify_reason=clarify_reason,
                clarify_message=self._hard_clarify_message(winner_owner, second_owner),
            )

        self._set_clarify_context(
            session_key=session_key,
            payload={
                "reason": clarify_reason,
                "candidate_owners": [winner_owner, second_owner],
                "best_owner": winner_owner,
                "attempt_count": 1 if not existing else int(existing.get("attempt_count") or 0) + 1,
                "written_turn": turn_index,
            },
        )
        return ArbitrationDecision(
            owner="clarify",
            confidence=max(winner_score, second_score),
            reason="clarify_required",
            scores=scores,
            query_type=query_type,
            clarify_reason=clarify_reason,
            clarify_message=self._clarify_message_for_reason(clarify_reason),
        )

    @staticmethod
    def _owner_domain(owner: str) -> str:
        if owner in {"entity_followup"}:
            return "entity"
        if owner in {"action_followup", "scheduling_command"}:
            return "action"
        if owner in {"profile_recall", "general_memory"}:
            return "memory"
        if owner in {"identity", "system_command"}:
            return "intent"
        return "chat"

    @staticmethod
    def _clarify_reason_from_owners(first: str, second: str) -> str:
        domains = {StateArbiter._owner_domain(first), StateArbiter._owner_domain(second)}
        if domains == {"entity", "action"}:
            return "ambiguous_entity_action"
        if domains == {"entity", "memory"}:
            return "ambiguous_profile_entity"
        if domains == {"action", "memory"}:
            return "ambiguous_action_memory"
        return "low_confidence"

    @staticmethod
    def _clarify_message_for_reason(reason: str) -> str:
        mapping = {
            "ambiguous_entity_action": "Do you mean your reminder, or the person we were discussing?",
            "ambiguous_profile_entity": "Are you asking about your profile info or the research topic?",
            "ambiguous_action_memory": "Are you asking about your reminder or your profile info?",
            "state_expired": "I don't have enough recent context. Can you restate what you mean?",
            "low_confidence": "I'm not fully sure which context you mean. Can you clarify?",
        }
        return mapping.get(reason, mapping["low_confidence"])

    @staticmethod
    def _hard_clarify_message(first_owner: str, second_owner: str) -> str:
        labels = {
            "entity_followup": "the person/topic we were discussing",
            "action_followup": "your reminder/alarm",
            "profile_recall": "your profile info",
            "general_memory": "something from earlier context",
            "scheduling_command": "a scheduling request",
            "identity": "my assistant identity",
        }
        first = labels.get(first_owner, first_owner)
        second = labels.get(second_owner, second_owner)
        return f"Please choose one: {first}, or {second}."

    def _get_clarify_context(self, *, session_key: str, turn_index: int) -> Optional[Dict[str, Any]]:
        payload = self._clarify_context.get(session_key)
        if not payload:
            return None
        written_turn = int(payload.get("written_turn") or 0)
        if (turn_index - written_turn) > self._clarify_memory_turns:
            self._clarify_context.pop(session_key, None)
            return None
        return dict(payload)

    def _set_clarify_context(self, *, session_key: str, payload: Dict[str, Any]) -> None:
        self._clarify_context[session_key] = dict(payload)

    def _clear_clarify_context(self, session_key: str) -> None:
        self._clarify_context.pop(session_key, None)

    @staticmethod
    def _short_scores(scores: Dict[str, float]) -> Dict[str, float]:
        return {k: round(float(v), 2) for k, v in scores.items() if v > 0}

    @staticmethod
    def _truthy_env(name: str, default: bool) -> bool:
        raw = os.getenv(name, "true" if default else "false")
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _float_env(name: str, default: float) -> float:
        try:
            return float(str(os.getenv(name, str(default))).strip())
        except Exception:
            return default

    @staticmethod
    def _int_env(name: str, default: int) -> int:
        try:
            return int(str(os.getenv(name, str(default))).strip())
        except Exception:
            return default
