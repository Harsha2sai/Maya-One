import asyncio
import logging
import os
from aiohttp import web
from .handlers import (
    handle_token,
    handle_health,
    handle_api_keys,
    handle_get_api_status,
    handle_send_message,
)

logger = logging.getLogger(__name__)

import sys
import atexit


# Singleton guard removed - LifecycleManager handles single instance
LOCK_FILE = "/tmp/maya_token_server.lock"

async def cors_middleware(app, handler):
    """CORS middleware for cross-origin requests from Flutter web/mobile"""
    async def middleware(request):
        if request.method == 'OPTIONS':
            resp = web.Response()
        else:
            resp = await handler(request)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp
    return middleware

async def run_token_server(port=5050, host='0.0.0.0'):
    """
    Async token server entrypoint.
    Designed to be run as a background task via asyncio.create_task().
    """
    logger.info(f"🚀 Starting Integrated Token Server (Async) on {host}:{port}...")
    
    app = web.Application()
    app.middlewares.append(cors_middleware)
    
    # Register routes
    from .handlers import (
        handle_upload,
        handle_token,
        handle_health,
        handle_api_keys,
        handle_get_api_status,
        handle_send_message,
    )
    app.router.add_post('/upload', handle_upload)
    app.router.add_post('/token', handle_token)
    app.router.add_post('/send_message', handle_send_message)
    app.router.add_get('/health', handle_health)
    app.router.add_post('/api-keys', handle_api_keys)
    app.router.add_get('/api-keys/status', handle_get_api_status)
    
    # Static files for uploads
    uploads_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    os.makedirs(uploads_path, exist_ok=True)
    app.router.add_static('/uploads/', uploads_path)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"✅ Token Server started on http://{host}:{port}")
    
    # Keep it running until the main loop stops
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    # For standalone testing only
    asyncio.run(run_token_server())
