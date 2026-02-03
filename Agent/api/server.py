import asyncio
import logging
from aiohttp import web
from .handlers import handle_token, handle_health, handle_api_keys, handle_get_api_status

logger = logging.getLogger(__name__)

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

def run_token_server(port=5050, host='0.0.0.0'):
    """Starts the token server using aiohttp in a sub-loop"""
    print(f"🚀 Starting Integrated Token Server on {host}:{port}...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = web.Application()
    app.middlewares.append(cors_middleware)
    
    # Register routes
    app.router.add_post('/token', handle_token)
    app.router.add_get('/health', handle_health)
    app.router.add_post('/api-keys', handle_api_keys)
    app.router.add_get('/api-keys/status', handle_get_api_status)
    
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, host, port)
    loop.run_until_complete(site.start())
    
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
