
import logging
from livekit.agents.utils import http_server

logger = logging.getLogger(__name__)

def apply_http_server_patch():
    """
    Monkeypatch LiveKit HttpServer.start to enable SO_REUSEADDR.
    This prevents OSError: [Errno 98] Address already in use during restarts.
    """
    logger.info("🔧 Applying LiveKit HttpServer patch (SO_REUSEADDR)...")
    
    original_start = http_server.HttpServer.start

    async def patched_start(self) -> None:
        required_attrs = ("_lock", "_app", "_loop", "_host", "_port")
        if any(not hasattr(self, attr) for attr in required_attrs):
            logger.info(
                "HttpServer internals changed; using original start() implementation"
            )
            await original_start(self)
            return

        async with self._lock:
            handler = self._app.make_handler()
            # FORCE reuse_address=True to allow immediate restart on same port
            self._server = await self._loop.create_server(
                handler, 
                self._host, 
                self._port, 
                reuse_address=True
            )

            if self._port == 0:
                self._port = self._server.sockets[0].getsockname()[1]

            await self._server.start_serving()

    # Apply the patch
    http_server.HttpServer.start = patched_start
    logger.info("✅ LiveKit HttpServer patch applied")
