import json
import sqlite3
from dataclasses import asdict, dataclass, field


@dataclass
class BuddyState:
    xp: int = 0
    level: int = 1
    stage: int = 1
    total_tasks: int = 0
    successful_tasks: int = 0
    current_mode: str = "standard"
    personality_traits: dict = field(default_factory=dict)


class BuddyMemory:
    XP_PER_LEVEL = 100
    STAGE_THRESHOLDS = {1: 0, 2: 200, 3: 500, 4: 1000, 5: 2000}

    def __init__(self, db_path: str = "dev_maya_one.db"):
        self._db = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        with sqlite3.connect(self._db) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS buddy_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def load(self) -> BuddyState:
        with sqlite3.connect(self._db) as conn:
            row = conn.execute(
                "SELECT value FROM buddy_state WHERE key = 'state'"
            ).fetchone()
        if row:
            return BuddyState(**json.loads(row[0]))
        return BuddyState()

    def save(self, state: BuddyState) -> None:
        with sqlite3.connect(self._db) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO buddy_state VALUES ('state', ?)",
                (json.dumps(asdict(state)),),
            )
