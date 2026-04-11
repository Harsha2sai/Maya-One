from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskOutcome:
    task_id: str
    agent_type: str
    prompt: str
    response: str
    success: bool
    route: str
    latency_ms: float
    tool_calls: List[str] = field(default_factory=list)
    user_rating: Optional[int] = None
    session_id: str = ""
    user_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)


class OutcomeLogger:
    """
    JSONL outcome logger used as the P37 RL data foundation.
    """

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = store_path or (Path.home() / ".maya" / "outcomes")
        self.store_path.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def log(self, outcome: TaskOutcome) -> None:
        path = self._daily_file()
        async with self._lock:
            try:
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(asdict(outcome), ensure_ascii=True) + "\n")
                logger.debug(
                    "outcome_logged task_id=%s agent=%s success=%s",
                    outcome.task_id,
                    outcome.agent_type,
                    outcome.success,
                )
            except Exception as exc:
                logger.warning("outcome_log_failed task_id=%s error=%s", outcome.task_id, exc)

    async def rate(self, task_id: str, rating: int) -> bool:
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be 1-5")

        path = self._daily_file()
        if not path.exists():
            return False

        updated = False
        lines: List[str] = []
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    lines.append(line)
                    continue
                if record.get("task_id") == task_id:
                    record["user_rating"] = rating
                    updated = True
                lines.append(json.dumps(record, ensure_ascii=True))

        if updated:
            async with self._lock:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("\n".join(lines) + "\n")

        return updated

    def iter_outcomes(
        self,
        days: int = 30,
        agent_type: Optional[str] = None,
        min_rating: Optional[int] = None,
        success_only: bool = False,
    ) -> Iterator[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        for path in sorted(self.store_path.glob("outcomes_*.jsonl")):
            with open(path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if not self._is_after_cutoff(record, cutoff):
                        continue
                    if agent_type and record.get("agent_type") != agent_type:
                        continue
                    if success_only and not bool(record.get("success")):
                        continue
                    if min_rating is not None:
                        rating = record.get("user_rating")
                        if rating is None or int(rating) < int(min_rating):
                            continue

                    yield record

    def stats(self, days: int = 7) -> Dict[str, object]:
        total = 0
        success = 0
        rated = 0
        rating_sum = 0
        by_agent: Dict[str, int] = {}
        by_route: Dict[str, int] = {}

        for record in self.iter_outcomes(days=days):
            total += 1
            if bool(record.get("success")):
                success += 1
            rating = record.get("user_rating")
            if rating is not None:
                rated += 1
                rating_sum += int(rating)
            agent = str(record.get("agent_type", "unknown"))
            route = str(record.get("route", "unknown"))
            by_agent[agent] = by_agent.get(agent, 0) + 1
            by_route[route] = by_route.get(route, 0) + 1

        return {
            "total": total,
            "success_rate": round(success / total, 3) if total else 0.0,
            "rated": rated,
            "avg_rating": round(rating_sum / rated, 2) if rated else None,
            "by_agent": by_agent,
            "by_route": by_route,
            "days": days,
        }

    def _daily_file(self) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.store_path / f"outcomes_{date_str}.jsonl"

    @staticmethod
    def _is_after_cutoff(record: dict, cutoff: datetime) -> bool:
        raw_ts = record.get("timestamp")
        if not raw_ts:
            return True
        try:
            ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts >= cutoff
        except Exception:
            return True

