import os
import subprocess
import logging
import sys

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("plugin-installer")

PLUGINS_REPOS = {
    "spotify": "https://github.com/varunneal/spotify-mcp",
    "reddit": "https://github.com/LobeHub/mcp-server-reddit",
    "youtube": "https://github.com/ZubeidHendricks/youtube-mcp-server",
    "google_maps": "https://github.com/cablate/mcp-google-map",
    "whatsapp": "https://github.com/lharries/whatsapp-mcp",
    "telegram": "https://github.com/sparfenyuk/mcp-telegram",
    "home_assistant": "https://github.com/homeassistant-ai/ha-mcp",
    "fal_ai": "https://github.com/raveenb/fal-mcp-server"
}

def install_plugin(name, repo_url):
    plugin_dir = os.path.join(os.path.dirname(__file__), name)
    mcp_server_dir = os.path.join(plugin_dir, "mcp_server")

    if not os.path.exists(plugin_dir):
        logger.info(f"Creating plugin directory: {plugin_dir}")
        os.makedirs(plugin_dir)

    if os.path.exists(mcp_server_dir):
        logger.info(f"Plugin {name} already has an mcp_server directory. Skipping clone.")
    else:
        logger.info(f"Cloning {name} from {repo_url}...")
        try:
            subprocess.run(["git", "clone", repo_url, mcp_server_dir], check=True)
            logger.info(f"✅ Successfully cloned {name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to clone {name}: {e}")
            return False

    # Try to install dependencies if requirements.txt exists
    req_path = os.path.join(mcp_server_dir, "requirements.txt")
    if os.path.exists(req_path):
        logger.info(f"Installing dependencies for {name}...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path], check=True)
            logger.info(f"✅ Successfully installed dependencies for {name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to install dependencies for {name}: {e}")

    return True

def main():
    logger.info("🚀 Starting Maya-One Plugin Auto-Installer")

    for name, repo in PLUGINS_REPOS.items():
        install_plugin(name, repo)

    logger.info("🏁 Plugin installation process finished.")

if __name__ == "__main__":
    main()
