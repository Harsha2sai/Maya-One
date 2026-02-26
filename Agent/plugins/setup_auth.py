import os
import json
import subprocess
import sys
import argparse
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("plugin-setup")

def run_interactive_setup(plugin_name):
    """
    Runs a plugin's MCP server in interactive mode so the user can scan QR codes,
    enter verification codes, or log in via browser.
    """
    plugin_dir = os.path.join(os.path.dirname(__file__), plugin_name)
    meta_path = os.path.join(plugin_dir, "plugin.json")

    if not os.path.exists(meta_path):
        logger.error(f"❌ Plugin {plugin_name} not found or missing plugin.json")
        return False

    with open(meta_path, 'r') as f:
        config = json.load(f)

    command = config.get("command")
    args = config.get("args", [])
    env = {**os.environ, **config.get("env", {})}

    # Resolve paths
    resolved_args = []
    for arg in args:
        if "{{PLUGIN_PATH}}" in arg:
            arg = arg.replace("{{PLUGIN_PATH}}", plugin_dir)
        resolved_args.append(arg)

    if not command:
        logger.error(f"❌ No command found for plugin {plugin_name}")
        return False

    logger.info(f"🚀 Starting interactive setup for {plugin_name}...")
    logger.info(f"📝 Command: {command} {' '.join(resolved_args)}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    try:
        # We run the command directly with full terminal access (stdin/stdout)
        subprocess.run([command] + resolved_args, env=env, check=True)
        logger.info(f"✅ Setup session finished for {plugin_name}")
    except KeyboardInterrupt:
        logger.info(f"\n🛑 Setup interrupted for {plugin_name}")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Setup command failed: {e}")

    return True

def main():
    parser = argparse.ArgumentParser(description="Maya-One Plugin Interactive Setup Utility")
    parser.add_argument("plugin", help="Name of the plugin folder to set up (e.g. 'whatsapp', 'telegram')")

    args = parser.parse_args()
    run_interactive_setup(args.plugin)

if __name__ == "__main__":
    main()
