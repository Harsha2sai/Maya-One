#!/usr/bin/env python3
"""
Send a test message to the running Maya agent via HTTP bridge.
Called by Dart integration tests.
Usage: python send_message.py "your message here"
"""
import sys
import asyncio
import aiohttp
import json

async def send(message: str):
    # Get token
    async with aiohttp.ClientSession() as session:
        async with session.get('http://localhost:5050/token') as resp:
            data = await resp.json()
            token = data['token']

        # Send message via agent bridge endpoint
        payload = {'message': message, 'token': token}
        async with session.post(
            'http://localhost:5050/send_message',
            json=payload
        ) as resp:
            result = await resp.json()
            print(json.dumps(result))
            return resp.status == 200

if __name__ == '__main__':
    message = sys.argv[1] if len(sys.argv) > 1 else 'hello'
    success = asyncio.run(send(message))
    sys.exit(0 if success else 1)
