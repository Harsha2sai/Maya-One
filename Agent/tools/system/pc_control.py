
import subprocess
import logging
import webbrowser
from typing import Optional
from livekit.agents import function_tool, RunContext

logger = logging.getLogger(__name__)

# Extended app mapping with more applications
APP_MAP = {
    # Browsers
    "chrome": "google-chrome",
    "google chrome": "google-chrome",
    "firefox": "firefox",
    "fire fox": "firefox",
    "mozilla firefox": "firefox",
    "browser": "google-chrome",
    "brave": "brave-browser",
    "edge": "microsoft-edge",
    
    # Communication
    "telegram": "telegram-desktop",
    "telegram desktop": "telegram-desktop",
    "discord": "discord",
    "slack": "slack",
    "whatsapp": "whatsapp-linux",  # Unofficial
    "teams": "teams",
    "zoom": "zoom",
    "skype": "skype",
    
    # Development
    "code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "vs code": "code",
    "sublime": "subl",
    "atom": "atom",
    "pycharm": "pycharm",
    "intellij": "idea",
    "android studio": "android-studio",
    
    # System Utils
    "calculator": "gnome-calculator",
    "calc": "gnome-calculator",
    "calcultor": "gnome-calculator",  # Common typo
    "calulator": "gnome-calculator",  # Common typo
    "terminal": "gnome-terminal",
    "term": "gnome-terminal",
    "console": "gnome-terminal",
    "settings": "gnome-control-center",
    "system settings": "gnome-control-center",
    "files": "nautilus",
    "file manager": "nautilus",
    "explorer": "nautilus",
    "file explorer": "nautilus",
    
    # Text Editors
    "notepad": "gedit",
    "editor": "gedit",
    "text editor": "gedit",
    "gedit": "gedit",
    "kate": "kate",
    "nano": "gnome-terminal -- nano",
    "vim": "gnome-terminal -- vim",
    
    # Media
    "vlc": "vlc",
    "media player": "vlc",
    "video player": "vlc",
    "spotify": "spotify",
    "music": "spotify",
    "rhythmbox": "rhythmbox",
    "audacity": "audacity",
    "gimp": "gimp",
    "image editor": "gimp",
    "obs": "obs",
    "obs studio": "obs",
    
    # Office
    "libreoffice": "libreoffice",
    "writer": "libreoffice --writer",
    "word": "libreoffice --writer",
    "calc": "libreoffice --calc",
    "excel": "libreoffice --calc",
    "spreadsheet": "libreoffice --calc",
    "impress": "libreoffice --impress",
    "powerpoint": "libreoffice --impress",
    "presentation": "libreoffice --impress",
    
    # Games / Entertainment
    "steam": "steam",
    "lutris": "lutris",
}

# Web URLs - these open in browser
WEB_MAP = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "whatsapp web": "https://web.whatsapp.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "docs": "https://docs.google.com",
    "sheets": "https://sheets.google.com",
    "maps": "https://maps.google.com",
}


def fuzzy_match(name: str, mapping: dict) -> Optional[str]:
    """Try to find a close match for typos."""
    name = name.lower().strip()
    
    # Direct match
    if name in mapping:
        return mapping[name]
    
    # Check if name is contained in any key
    for key, value in mapping.items():
        if name in key or key in name:
            return value
    
    # Simple Levenshtein-like matching for typos
    for key in mapping:
        if len(name) >= 3 and len(key) >= 3:
            # Check if most characters match
            common = sum(1 for a, b in zip(name, key) if a == b)
            if common >= len(min(name, key)) * 0.7:  # 70% match
                logger.info(f"🔍 Fuzzy matched '{name}' to '{key}'")
                return mapping[key]
    
    return None


@function_tool(name="open_app")
async def open_app(context: RunContext, app_name: str) -> str:
    """
    Open an application or website on the user's computer.
    
    Args:
        app_name: The name of the application or website to open 
                  (e.g. "chrome", "firefox", "calculator", "youtube", "telegram")
    """
    import string
    
    # Normalize app name
    normalized_name = app_name.lower().strip()
    normalized_name = normalized_name.strip(string.punctuation)
    
    logger.info(f"🚀 Attempting to open: {normalized_name}")
    
    # 1. Check if it's a web URL first
    web_url = fuzzy_match(normalized_name, WEB_MAP)
    if web_url:
        try:
            logger.info(f"🌐 Opening web URL: {web_url}")
            webbrowser.open(web_url)
            return f"Opened {app_name} in your browser"
        except Exception as e:
            logger.error(f"Failed to open URL {web_url}: {e}")
            return f"Failed to open {app_name}: {e}"
    
    # 2. Check if it's an application
    command = fuzzy_match(normalized_name, APP_MAP)
    
    # 3. If no match found, try the raw name
    if not command:
        command = normalized_name
        logger.info(f"⚠️ No mapping found, trying raw command: {command}")
    
    try:
        # Use subprocess.Popen to run without blocking
        subprocess.Popen(
            command, 
            shell=True, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Fully detach from parent
        )
        logger.info(f"✅ Successfully launched: {command}")
        return f"Opened {app_name}"
    except Exception as e:
        logger.error(f"Failed to open app {app_name}: {e}")
        return f"Failed to open {app_name}: {e}"

@function_tool(name="close_app")
async def close_app(context: RunContext, app_name: str) -> str:
    """
    Close (kill) an application.
    
    Args:
        app_name: The name of the application to close
    """
    logger.info(f"🛑 Attempting to close app: {app_name}")
    
    try:
        subprocess.run(["pkill", "-f", app_name], check=True)
        return f"Closed {app_name}"
    except subprocess.CalledProcessError:
        return f"Could not find running process for {app_name}"
    except Exception as e:
        return f"Error closing {app_name}: {e}"
