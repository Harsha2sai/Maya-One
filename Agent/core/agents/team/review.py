"""Review primitives for Team Mode aggregation and release gating."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Iterable, List


class ReviewSeverity(IntEnum):
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


@dataclass
class ReviewFinding:
    severity: ReviewSeverity
    message: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewSummary:
    total: int
    counts: dict[str, int]
    highest_severity: str
    should_block: bool


class ReviewReducer:
    """Normalizes findings and computes blocking summaries."""

    _SEVERITY_ALIASES = {
        "info": ReviewSeverity.INFO,
        "low": ReviewSeverity.INFO,
        "warning": ReviewSeverity.WARNING,
        "warn": ReviewSeverity.WARNING,
        "medium": ReviewSeverity.WARNING,
        "error": ReviewSeverity.ERROR,
        "high": ReviewSeverity.ERROR,
        "critical": ReviewSeverity.CRITICAL,
        "blocker": ReviewSeverity.CRITICAL,
    }

    @classmethod
    def coerce_severity(cls, value: Any) -> ReviewSeverity:
        if isinstance(value, ReviewSeverity):
            return value
        if isinstance(value, int):
            try:
                return ReviewSeverity(value)
            except ValueError:
                return ReviewSeverity.WARNING
        normalized = str(value or "").strip().lower()
        return cls._SEVERITY_ALIASES.get(normalized, ReviewSeverity.WARNING)

    @classmethod
    def normalize_finding(cls, raw: Any) -> ReviewFinding:
        if isinstance(raw, ReviewFinding):
            return raw
        if isinstance(raw, dict):
            return ReviewFinding(
                severity=cls.coerce_severity(raw.get("severity")),
                message=str(raw.get("message") or ""),
                source=str(raw.get("source") or ""),
                metadata=dict(raw.get("metadata") or {}),
            )
        return ReviewFinding(
            severity=ReviewSeverity.WARNING,
            message=str(raw or ""),
        )

    @classmethod
    def merge_findings(cls, *groups: Iterable[Any]) -> List[ReviewFinding]:
        merged: List[ReviewFinding] = []
        for group in groups:
            for item in group or []:
                merged.append(cls.normalize_finding(item))
        return merged

    @classmethod
    def should_block(
        cls,
        findings: Iterable[Any],
        *,
        threshold: ReviewSeverity = ReviewSeverity.ERROR,
    ) -> bool:
        normalized = cls.merge_findings(findings)
        if not normalized:
            return False
        highest = max(item.severity for item in normalized)
        return highest >= threshold

    @classmethod
    def summarize(
        cls,
        findings: Iterable[Any],
        *,
        threshold: ReviewSeverity = ReviewSeverity.ERROR,
    ) -> ReviewSummary:
        normalized = cls.merge_findings(findings)
        counts = {
            "info": 0,
            "warning": 0,
            "error": 0,
            "critical": 0,
        }
        highest = ReviewSeverity.INFO
        for item in normalized:
            if item.severity == ReviewSeverity.INFO:
                counts["info"] += 1
            elif item.severity == ReviewSeverity.WARNING:
                counts["warning"] += 1
            elif item.severity == ReviewSeverity.ERROR:
                counts["error"] += 1
            else:
                counts["critical"] += 1
            if item.severity > highest:
                highest = item.severity

        return ReviewSummary(
            total=len(normalized),
            counts=counts,
            highest_severity=highest.name.lower(),
            should_block=highest >= threshold if normalized else False,
        )
