"""Route precedence and conflict-resolution helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from core.action.constants import RoutePrecedence


@dataclass(frozen=True)
class RouteCandidate:
    route: str
    precedence: RoutePrecedence
    target: str = ""
    destructive: bool = False
    confidence: float = 1.0


@dataclass(frozen=True)
class RouteResolution:
    route: str
    ask_clarification: bool
    reason: str


class RoutePrecedenceResolver:
    def resolve(self, candidates: Iterable[RouteCandidate]) -> RouteResolution:
        items = [c for c in candidates if str(c.route or "").strip()]
        if not items:
            return RouteResolution(route="chat", ask_clarification=False, reason="no_candidates")

        sorted_items = sorted(items, key=lambda c: (int(c.precedence), -float(c.confidence or 0.0)))
        winner = sorted_items[0]
        same_rank = [
            c
            for c in sorted_items
            if int(c.precedence) == int(winner.precedence)
        ]
        if len(same_rank) > 1:
            distinct_targets = {str(c.target or "").strip().lower() for c in same_rank if str(c.target or "").strip()}
            if len(distinct_targets) > 1:
                destructive_present = any(c.destructive for c in same_rank)
                return RouteResolution(
                    route="chat",
                    ask_clarification=True,
                    reason="destructive_target_conflict" if destructive_present else "target_conflict",
                )
        return RouteResolution(route=winner.route, ask_clarification=False, reason="highest_precedence")

