#!/usr/bin/env python3
"""
Test Bridge Server for Maya-One Integration Tests
Provides HTTP endpoints for Dart integration tests to:
- Get LiveKit session tokens (/token)
- Send test messages to the orchestrator (/send_message)

Usage: python test_bridge_server.py [--port 5050]
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    from aiohttp import web
except ImportError:
    print("ERROR: aiohttp not installed. Run: pip install aiohttp")
    sys.exit(1)

# Import from agent codebase
sys.path.insert(0, os.path.dirname(__file__))

# This will be set by the integration test runner
TEST_SESSION_ID = os.environ.get("MAYA_TEST_SESSION", "test_session_001")
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")


async def handle_token(request: web.Request) -> web.Response:
    """
    /token endpoint: Return a LiveKit session token for integration tests.
    This simulates what the Flutter frontend would do to get credentials.
    """
    try:
        from livekit import AccessToken, TokenVerifier
        
        # Create a token for the test participant
        token = AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.identity = f"test_user_{TEST_SESSION_ID}"
        token.name = "Integration Test User"
        token.add_grant({"canPublish": True, "canPublishData": True, "canSubscribe": True})
        
        response = {
            "token": token.to_jwt().decode("utf-8"),
            "url": LIVEKIT_URL,
            "user": token.identity,
        }
        logger.info(f"✓ Token issued for {token.identity}")
        return web.json_response(response)
    
    except Exception as e:
        logger.error(f"✗ Token generation failed: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_send_message(request: web.Request) -> web.Response:
    """
    /send_message endpoint: Accept a test message and inject it into the
    running orchestrator for integration testing.
    
    Request body:
    {
        "message": "the user message",
        "token": "livekit session token"  (optional)
    }
    """
    try:
        body = await request.json()
        message = body.get("message", "").strip()
        user_token = body.get("token")
        
        if not message:
            return web.json_response({"error": "no message"}, status=400)
        
        # Inject the message into the global orchestrator if available
        try:
            from core.runtime.global_agent import GlobalAgentContainer
            
            container = GlobalAgentContainer.get_instance()
            if not container or not container.orchestrator:
                logger.warning("⚠ Orchestrator not available for message injection")
                return web.json_response({
                    "status": "no_session",
                    "routed": False,
                    "message": "Orchestrator not initialized"
                })
            
            # Send the message to the orchestrator
            # This simulates what LiveKit would do with an incoming chat message
            result = await container.orchestrator.handle_user_message(
                message=message,
                user_id=f"test_user_{TEST_SESSION_ID}",
                session_id=f"test_session_{TEST_SESSION_ID}"
            )
            
            logger.info(f"✓ Message routed: {message[:50]}...")
            return web.json_response({
                "status": "ok",
                "routed": True,
                "message_length": len(message),
            })
        
        except ImportError:
            logger.warning("⚠ GlobalAgentContainer not available")
            return web.json_response({
                "status": "not_ready",
                "routed": False,
            })
    
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid json"}, status=400)
    except Exception as e:
        logger.error(f"✗ Message routing failed: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def healthz(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({"status": "ok"})


async def start_server(port: int = 5050) -> web.AppRunner:
    """Start the test bridge server."""
    app = web.Application()
    
    # Routes
    app.router.add_get('/healthz', healthz)
    app.router.add_get('/token', handle_token)
    app.router.add_post('/send_message', handle_send_message)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"🚀 Test Bridge Server listening on 0.0.0.0:{port}")
    logger.info(f"   - GET  /healthz")
    logger.info(f"   - GET  /token")
    logger.info(f"   - POST /send_message")
    
    return runner


async def main():
    """Run the server."""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
    runner = await start_server(port)
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
