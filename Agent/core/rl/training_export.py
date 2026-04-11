from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from core.rl.outcome_logger import OutcomeLogger

logger = logging.getLogger(__name__)


class TrainingExporter:
    """
    Export outcomes to Trinity-RFT style JSONL.
    """

    LATENCY_PENALTY_MS = 10_000
    LATENCY_PENALTY = 0.1

    def __init__(self, outcome_logger: OutcomeLogger):
        self.logger = outcome_logger

    def export(
        self,
        output_path: Path,
        days: int = 30,
        min_rating: Optional[int] = None,
        agent_type: Optional[str] = None,
        success_only: bool = True,
    ) -> int:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(output_path, "w", encoding="utf-8") as handle:
            for record in self.logger.iter_outcomes(
                days=days,
                agent_type=agent_type,
                min_rating=min_rating,
                success_only=success_only,
            ):
                example = {
                    "prompt": record.get("prompt", ""),
                    "response": record.get("response", ""),
                    "reward": self._compute_reward(record),
                    "_task_id": record.get("task_id"),
                    "_agent_type": record.get("agent_type"),
                    "_route": record.get("route"),
                }
                handle.write(json.dumps(example, ensure_ascii=True) + "\n")
                count += 1
        logger.info("training_export_complete records=%s output=%s", count, output_path)
        return count

    def _compute_reward(self, record: dict) -> float:
        reward = 1.0 if bool(record.get("success")) else 0.0
        rating = record.get("user_rating")
        if rating is not None:
            bonus = ((int(rating) - 1) / 4) * 0.2
            reward = min(1.0, reward + bonus)

        latency = float(record.get("latency_ms", 0) or 0)
        if latency > self.LATENCY_PENALTY_MS:
            reward = max(0.0, reward - self.LATENCY_PENALTY)
        return round(reward, 4)

