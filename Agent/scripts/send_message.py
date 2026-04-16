#!/usr/bin/env python3
"""Send one text turn through the local token+bridge flow.

Usage:
    python scripts/send_message.py "hello maya"
"""

import argparse
import asyncio
import json
import time
import uuid
from typing import Any, Dict, Tuple

import aiohttp

DEFAULT_BASE_URL = "http://127.0.0.1:5050"


def _build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one message to Maya bridge")
    parser.add_argument("message", nargs="?", default="hello")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--room", default="")
    parser.add_argument("--participant", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


async def _post_json(
    session: aiohttp.ClientSession,
    url: str,
    payload: Dict[str, Any],
    timeout_s: float,
) -> Tuple[int, Dict[str, Any]]:
    async with session.post(url, json=payload, timeout=timeout_s) as resp:
        text = await resp.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"raw": text}
        return resp.status, data


async def send(
    message: str,
    *,
    base_url: str,
    room: str,
    participant: str,
    run_id: str,
    timeout_s: float,
) -> bool:
    room_name = room or f"sendmsg-{int(time.time())}"
    participant_name = participant or f"probe-{uuid.uuid4().hex[:8]}"
    run_identifier = run_id or room_name
    token_url = f"{base_url.rstrip('/')}/token"
    send_url = f"{base_url.rstrip('/')}/send_message"

    async with aiohttp.ClientSession() as session:
        token_status, token_data = await _post_json(
            session,
            token_url,
            {"roomName": room_name, "participantName": participant_name, "metadata": {"source": "send_message.py"}},
            timeout_s,
        )
        if token_status != 200:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "step": "token",
                        "status": token_status,
                        "response": token_data,
                    }
                )
            )
            return False

        send_status, send_data = await _post_json(
            session,
            send_url,
            {
                "message": message,
                "user_id": participant_name,
                "run_id": run_identifier,
            },
            timeout_s,
        )

        payload = {
            "ok": send_status == 200,
            "token_status": token_status,
            "send_status": send_status,
            "room": room_name,
            "participant": participant_name,
            "run_id": run_identifier,
            "send_response": send_data,
        }
        print(json.dumps(payload))
        return send_status == 200


if __name__ == "__main__":
    args = _build_args()
    success = asyncio.run(
        send(
            args.message,
            base_url=args.base_url,
            room=args.room,
            participant=args.participant,
            run_id=args.run_id,
            timeout_s=args.timeout,
        )
    )
    raise SystemExit(0 if success else 1)
