import asyncio
import logging
import os
from aiohttp import web
from dotenv import load_dotenv
from .handlers import (
    handle_ide_action_approve,
    handle_ide_action_audit,
    handle_ide_action_cancel,
    handle_ide_action_deny,
    handle_ide_action_pending,
    handle_ide_action_request,
    handle_ide_file_read,
    handle_ide_file_write,
    handle_ide_files_tree,
    handle_ide_events_stream,
    handle_ide_mcp_inventory,
    handle_ide_mcp_mutate,
    handle_ide_session_close,
    handle_ide_session_open,
    handle_ide_terminal_open,
    handle_ide_terminal_close,
    handle_ide_terminal_resize,
    handle_terminal_websocket,
    handle_token,
    handle_health,
    handle_ready,
    handle_api_keys,
    handle_get_api_status,
    handle_send_message,
)

logger = logging.getLogger(__name__)

# Ensure standalone token-server mode resolves the same .env values as agent boot.
load_dotenv()

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
        handle_ide_action_approve,
        handle_ide_action_audit,
        handle_ide_action_cancel,
        handle_ide_action_deny,
        handle_ide_action_pending,
        handle_ide_action_request,
        handle_ide_file_read,
        handle_ide_file_write,
        handle_ide_files_tree,
        handle_ide_events_stream,
        handle_ide_mcp_inventory,
        handle_ide_mcp_mutate,
        handle_ide_session_close,
        handle_ide_session_open,
        handle_token,
        handle_health,
        handle_ready,
        handle_api_keys,
        handle_get_api_status,
        handle_send_message,
    )
    app.router.add_post('/upload', handle_upload)
    app.router.add_post('/token', handle_token)
    app.router.add_post('/send_message', handle_send_message)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/ready', handle_ready)
    app.router.add_post('/api-keys', handle_api_keys)
    app.router.add_get('/api-keys/status', handle_get_api_status)
    app.router.add_post('/ide/session/open', handle_ide_session_open)
    app.router.add_post('/ide/session/close', handle_ide_session_close)
    app.router.add_get('/ide/files/tree', handle_ide_files_tree)
    app.router.add_get('/ide/file/read', handle_ide_file_read)
    app.router.add_post('/ide/file/write', handle_ide_file_write)
    app.router.add_get('/ide/events/stream', handle_ide_events_stream)
    app.router.add_post('/ide/action/request', handle_ide_action_request)
    app.router.add_get('/ide/action/pending', handle_ide_action_pending)
    app.router.add_get('/ide/action/audit', handle_ide_action_audit)
    app.router.add_post('/ide/action/approve', handle_ide_action_approve)
    app.router.add_post('/ide/action/deny', handle_ide_action_deny)
    app.router.add_post('/ide/action/cancel', handle_ide_action_cancel)
    app.router.add_get('/ide/mcp/inventory', handle_ide_mcp_inventory)
    app.router.add_post('/ide/mcp/mutate', handle_ide_mcp_mutate)
    app.router.add_post('/ide/terminal/open', handle_ide_terminal_open)
    app.router.add_post('/ide/terminal/close', handle_ide_terminal_close)
    app.router.add_post('/ide/terminal/resize', handle_ide_terminal_resize)
    app.router.add_get('/ws/terminal', handle_terminal_websocket)
    
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
