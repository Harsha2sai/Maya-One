"""Canonical action contracts for execution intent, receipts, and verification."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VerificationTier(str, Enum):
    strong = "strong"
    medium = "medium"
    weak = "weak"
    inconclusive = "inconclusive"
    failed = "failed"


@dataclass
class ActionIntent:
    intent_id: str
    session_id: str
    turn_id: str
    trace_id: str
    source_route: str
    target: str
    operation: str
    entity: str
    query: str
    confidence: float
    requires_confirmation: bool
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    intent_id: str
    tier: VerificationTier
    verified: bool
    confidence: float
    method: str
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    checked_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["tier"] = self.tier.value
        return payload


@dataclass
class ToolReceipt:
    receipt_id: str
    intent_id: str
    tool_name: str
    success: bool
    status: str
    executed: bool
    error_code: str
    message: str
    raw_result: Any
    normalized_result: Dict[str, Any]
    duration_ms: int
    timestamp: str = field(default_factory=_utc_now_iso)
    verification: Optional[VerificationResult] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.verification is not None:
            payload["verification"] = self.verification.to_dict()
        return payload

