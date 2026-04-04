#!/usr/bin/env python3
"""
Seed or update preferences for a given user_id.

Usage:
    python scripts/seed_preferences.py --user console_user --set music_app=spotify
    python scripts/seed_preferences.py --user console_user --set music_genre=lo-fi
    python scripts/seed_preferences.py --user console_user --dump
"""
import argparse
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from core.memory.preference_manager import PreferenceManager


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or inspect user preferences")
    parser.add_argument("--user", required=True, help="user_id to operate on")
    parser.add_argument(
        "--set",
        metavar="KEY=VALUE",
        action="append",
        dest="sets",
        help="Set a preference key=value (repeatable)",
    )
    parser.add_argument("--dump", action="store_true", help="Print current preferences")
    args = parser.parse_args()

    pm = PreferenceManager()

    if args.sets:
        for pair in args.sets:
            if "=" not in pair:
                print(f"ERROR: invalid format '{pair}', expected KEY=VALUE", file=sys.stderr)
                sys.exit(1)
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()
            ok = await pm.set(args.user, key, value)
            status = "OK" if ok else "FAILED"
            print(f"[{status}] {args.user}.{key} = {value}")

    if args.dump or not args.sets:
        prefs = await pm.get_all(args.user)
        print(json.dumps(prefs, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
