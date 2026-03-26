#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from core.events.agent_events import chat_event_json_schema


def _render_schema() -> str:
    schema = chat_event_json_schema()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def _write_or_check(path: Path, content: str, check: bool) -> bool:
    if check:
        if not path.exists():
            print(f"schema missing: {path}")
            return False
        current = path.read_text(encoding="utf-8")
        if current != content:
            print(f"schema drift detected: {path}")
            return False
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote schema: {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Export versioned chat event JSON Schema")
    parser.add_argument("--check", action="store_true", help="Do not write; fail on drift")
    parser.add_argument(
        "--output",
        action="append",
        default=[],
        help="Optional output path override (can be provided multiple times)",
    )
    args = parser.parse_args()

    agent_dir = AGENT_DIR
    repo_root = agent_dir.parent
    if args.output:
        targets = [Path(path).resolve() for path in args.output]
    else:
        targets = [
            agent_dir / "generated" / "agent_events.schema.v1.json",
            repo_root / "agent-starter-flutter-main" / "assets" / "schemas" / "agent_events.schema.v1.json",
        ]

    content = _render_schema()
    ok = True
    for target in targets:
        ok = _write_or_check(target, content, check=args.check) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
