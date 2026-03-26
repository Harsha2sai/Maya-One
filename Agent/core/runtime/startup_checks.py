import socket
import logging
from config.settings import settings

logger = logging.getLogger(__name__)

def check_port_free(port):
    """Check if a port is free by trying to bind to it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()

def validate_voice_plugins():
    """Checks for necessary LiveKit plugins."""
    from importlib.util import find_spec
    plugins = [
        ("livekit.plugins.deepgram", "deepgram"),
        ("livekit.plugins.silero", "silero"),
        ("livekit.plugins.openai", "openai"),
        ("livekit.plugins.cartesia", "cartesia")
    ]
    
    missing = []
    for spec_name, p_name in plugins:
        if find_spec(spec_name) is None:
            missing.append(p_name)
    
    if missing:
        logger.warning(f"⚠️ Missing voice plugins: {missing}. Some functionality may fail.")

def run_startup_checks(*, require_runtime_ports: bool = True):
    """
    Final production pre-flight checks.
    Ensures ports are available and critical plugins are present.
    """
    logger.info("🏥 Running Production Startup Checks...")

    if require_runtime_ports:
        worker_port = getattr(settings, "livekit_port", 8082)

        # Worker mode requires token server and LiveKit worker ports.
        assert check_port_free(5050), "Port 5050 (Token Server) still busy"
        assert check_port_free(worker_port), f"Port {worker_port} (LiveKit Worker HTTP) still busy"
    else:
        logger.info("ℹ️ Skipping worker runtime port checks for console mode")

    # Check Plugins
    validate_voice_plugins()
    
    logger.info("✅ Startup checks passed")
