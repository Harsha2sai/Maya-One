
import subprocess
import logging
import webbrowser
import shlex
import shutil
import os
import json
import re
import difflib
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus
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
    "whatsapp": "whatsdesk",
    "whatsapp desktop": "whatsdesk",
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
    "my files": "nautilus",
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
    "music player": "spotify",
    "songs": "spotify",
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
    "calc spreadsheet": "libreoffice --calc",
    "excel": "libreoffice --calc",
    "spreadsheet": "libreoffice --calc",
    "impress": "libreoffice --impress",
    "powerpoint": "libreoffice --impress",
    "presentation": "libreoffice --impress",
    
    # Games / Entertainment
    "steam": "steam",
    "lutris": "lutris",
}

APP_COMMAND_ALTERNATIVES = {
    "telegram": [
        "telegram-desktop",
        "telegram",
        "flatpak run org.telegram.desktop",
        "snap run telegram-desktop",
    ],
    "telegram desktop": [
        "telegram-desktop",
        "flatpak run org.telegram.desktop",
        "snap run telegram-desktop",
    ],
    "whatsapp": [
        "whatsdesk",
        "whatsapp-linux",
        "snap run whatsdesk",
    ],
    "whatsapp desktop": [
        "whatsdesk",
        "whatsapp-linux",
        "snap run whatsdesk",
    ],
}

# Web URLs - these open in browser
WEB_MAP = {
    "youtube": "https://www.youtube.com",
    "youtube music": "https://music.youtube.com",
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
    "telegram": "https://web.telegram.org",
    "telegram web": "https://web.telegram.org",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "docs": "https://docs.google.com",
    "sheets": "https://sheets.google.com",
    "maps": "https://maps.google.com",
    "spotify": "https://open.spotify.com",
    "music": "https://music.youtube.com",
    "songs": "https://music.youtube.com",
}

NO_WEB_FALLBACK_APPS = {
    "telegram",
    "telegram desktop",
    "whatsapp",
}

APP_CACHE_PATH = Path.home() / ".maya" / "cache" / "installed_apps.json"
APP_CACHE_MAX_AGE_SECONDS = 6 * 60 * 60
_APP_CACHE_MEMORY: Optional[dict[str, str]] = None
_APP_CACHE_LAST_SCAN: float = 0.0


def fuzzy_match(name: str, mapping: dict) -> Optional[str]:
    """Try to find a close match for typos with strict scoring."""
    name = name.lower().strip()

    # Direct match
    if name in mapping:
        return mapping[name]

    compact_name = name.replace(" ", "")

    # Compact exact match (handles e.g. "fire fox" vs "firefox")
    for key, value in mapping.items():
        if key.replace(" ", "") == compact_name:
            return value

    # Prefix containment with minimum token length to avoid false positives
    # like "whatsapp" matching "chat".
    for key, value in mapping.items():
        if len(name) >= 4 and len(key) >= 4 and (key.startswith(name) or name.startswith(key)):
            return value

    # Similarity-based fallback.
    candidates = [
        (key, difflib.SequenceMatcher(None, name, key).ratio())
        for key in mapping.keys()
        if len(key) >= 3
    ]
    if not candidates:
        return None
    best_key, best_score = max(candidates, key=lambda item: item[1])
    if best_score >= 0.84:
        logger.info(f"🔍 Fuzzy matched '{name}' to '{best_key}' (score={best_score:.2f})")
        return mapping[best_key]

    return None

def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except Exception:
        return [command]

def _primary_executable(parts: list[str]) -> Optional[str]:
    if not parts:
        return None
    if parts[0] != "env":
        return parts[0]
    i = 1
    while i < len(parts) and "=" in parts[i] and not parts[i].startswith("-"):
        i += 1
    if i >= len(parts):
        return None
    return parts[i]

def _is_installed(command: str) -> bool:
    parts = _split_command(command)
    if not parts:
        return False

    # Wrapper commands need deeper checks.
    if Path(parts[0]).name == "flatpak" and len(parts) >= 3 and parts[1] == "run":
        if shutil.which("flatpak") is None:
            return False
        app_id = next(
            (
                token
                for token in reversed(parts[2:])
                if re.fullmatch(r"[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+", token)
            ),
            None,
        )
        if not app_id:
            return False
        result = subprocess.run(
            ["flatpak", "info", app_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    if Path(parts[0]).name == "snap" and len(parts) >= 3 and parts[1] == "run":
        if shutil.which("snap") is None:
            return False
        app_name = parts[2]
        result = subprocess.run(
            ["snap", "list", app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    executable = _primary_executable(parts)
    if not executable:
        return False
    return shutil.which(executable) is not None


def _normalize_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").lower().strip())


def _parse_desktop_exec(exec_value: str) -> Optional[str]:
    """Parse .desktop Exec command and remove placeholder args like %u."""
    if not exec_value:
        return None
    # Drop field codes defined by desktop entry spec.
    cleaned = re.sub(r"\s+%[a-zA-Z]", "", exec_value).strip()
    cleaned = re.sub(r"\s+@@[a-zA-Z]", "", cleaned).strip()
    cleaned = cleaned.replace(" @@", "").replace("@@ ", " ").strip()

    # Normalize flatpak launcher commands to stable form.
    parts = _split_command(cleaned)
    if len(parts) >= 3 and Path(parts[0]).name == "flatpak" and parts[1] == "run":
        app_id = next(
            (
                token
                for token in reversed(parts[2:])
                if re.fullmatch(r"[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+", token)
            ),
            None,
        )
        if app_id:
            return f"flatpak run {app_id}"

    return cleaned or None


def _scan_desktop_entries() -> dict[str, str]:
    """
    Build name->command map from desktop launcher files.
    """
    index: dict[str, str] = {}
    desktop_dirs = [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        Path.home() / ".local/share/flatpak/exports/share/applications",
    ]

    for directory in desktop_dirs:
        if not directory.exists():
            continue
        for entry in directory.glob("*.desktop"):
            try:
                content = entry.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            desktop_id = _normalize_key(entry.stem)
            name_line = ""
            exec_line = ""
            for line in content.splitlines():
                if line.startswith("Name=") and not name_line:
                    name_line = _normalize_key(line.split("=", 1)[1])
                elif line.startswith("Exec=") and not exec_line:
                    exec_line = line.split("=", 1)[1].strip()
                if name_line and exec_line:
                    break

            candidate = _parse_desktop_exec(exec_line)
            if not candidate or not _is_installed(candidate):
                continue

            if name_line:
                index[name_line] = candidate
            if desktop_id:
                index[desktop_id] = candidate

    return index


def _scan_path_executables() -> dict[str, str]:
    """
    Build executable-name index from PATH directories.
    """
    index: dict[str, str] = {}
    for path_dir in os.getenv("PATH", "").split(":"):
        directory = Path(path_dir.strip())
        if not directory.exists() or not directory.is_dir():
            continue
        try:
            for child in directory.iterdir():
                if not child.is_file():
                    continue
                name = _normalize_key(child.name)
                if not name:
                    continue
                if os.access(child, os.X_OK):
                    index.setdefault(name, child.name)
        except Exception:
            continue
    return index


def _scan_snap_apps() -> dict[str, str]:
    """
    Build app index from snap packages.
    """
    index: dict[str, str] = {}
    if shutil.which("snap") is None:
        return index
    try:
        proc = subprocess.run(
            ["snap", "list"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return index
        lines = proc.stdout.splitlines()
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            name = line.split()[0].strip()
            if not name:
                continue
            normalized = _normalize_key(name)
            # `snap run <name>` is the most portable launcher across systems.
            index[normalized] = f"snap run {name}"
    except Exception:
        return index
    return index


def _scan_flatpak_apps() -> dict[str, str]:
    """
    Build app index from flatpak installed applications.
    """
    index: dict[str, str] = {}
    if shutil.which("flatpak") is None:
        return index
    try:
        proc = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application,name"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return index
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            # Typical output is tab-separated: <application>\t<name>
            parts = [p.strip() for p in re.split(r"\t+", line) if p.strip()]
            app_id = parts[0]
            display_name = parts[1] if len(parts) > 1 else parts[0]
            command = f"flatpak run {app_id}"
            index[_normalize_key(app_id)] = command
            index[_normalize_key(display_name)] = command
    except Exception:
        return index
    return index


def _scan_installed_apps() -> dict[str, str]:
    """
    Scan installed local apps and produce normalized alias -> launch command map.
    """
    index: dict[str, str] = {}

    # Seed with known aliases that actually exist on this machine.
    for alias, command in APP_MAP.items():
        if _is_installed(command):
            index[_normalize_key(alias)] = command

    # Seed known alternatives (telegram/whatsapp variants, etc.).
    for alias, alternatives in APP_COMMAND_ALTERNATIVES.items():
        for command in alternatives:
            if _is_installed(command):
                index.setdefault(_normalize_key(alias), command)
                break

    # Desktop launchers provide user-facing app names.
    desktop_index = _scan_desktop_entries()
    for alias, command in desktop_index.items():
        index.setdefault(alias, command)

    # PATH executable names as last-resort direct launches.
    path_index = _scan_path_executables()
    for alias, command in path_index.items():
        index.setdefault(alias, command)

    # Package manager app indexes.
    snap_index = _scan_snap_apps()
    for alias, command in snap_index.items():
        index.setdefault(alias, command)

    flatpak_index = _scan_flatpak_apps()
    for alias, command in flatpak_index.items():
        index.setdefault(alias, command)

    return index


def _read_cached_index() -> Optional[dict[str, str]]:
    try:
        if not APP_CACHE_PATH.exists():
            return None
        payload = json.loads(APP_CACHE_PATH.read_text(encoding="utf-8"))
        generated_at = float(payload.get("generated_at", 0))
        apps = payload.get("apps", {})
        if not isinstance(apps, dict):
            return None
        if (datetime.now().timestamp() - generated_at) > APP_CACHE_MAX_AGE_SECONDS:
            return None
        return {str(k): str(v) for k, v in apps.items()}
    except Exception:
        return None


def _write_cached_index(index: dict[str, str]) -> None:
    try:
        APP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now().timestamp(),
            "apps": index,
        }
        APP_CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed writing app cache: {e}")


def _get_installed_app_index(force_refresh: bool = False) -> dict[str, str]:
    global _APP_CACHE_MEMORY, _APP_CACHE_LAST_SCAN

    now = datetime.now().timestamp()
    if not force_refresh and _APP_CACHE_MEMORY is not None:
        if (now - _APP_CACHE_LAST_SCAN) < APP_CACHE_MAX_AGE_SECONDS:
            return _APP_CACHE_MEMORY

    if not force_refresh:
        cached = _read_cached_index()
        if cached:
            _APP_CACHE_MEMORY = cached
            _APP_CACHE_LAST_SCAN = now
            return cached

    scanned = _scan_installed_apps()
    _APP_CACHE_MEMORY = scanned
    _APP_CACHE_LAST_SCAN = now
    _write_cached_index(scanned)
    logger.info(f"🗂️ Installed app index refreshed ({len(scanned)} entries)")
    return scanned


def _resolve_installed_command(app_name: str) -> Optional[str]:
    """
    Resolve the best installed local app command with strict local-first priority.
    """
    normalized = _normalize_key(app_name)
    index = _get_installed_app_index()

    # Priority 1: explicit alias map and alternatives.
    explicit_candidates = []
    mapped = APP_MAP.get(normalized)
    if mapped:
        explicit_candidates.append(mapped)
    explicit_candidates.extend(APP_COMMAND_ALTERNATIVES.get(normalized, []))
    if "telegram" in normalized:
        explicit_candidates.extend(APP_COMMAND_ALTERNATIVES.get("telegram", []))
    if "whatsapp" in normalized:
        explicit_candidates.extend(APP_COMMAND_ALTERNATIVES.get("whatsapp", []))
    for candidate in explicit_candidates:
        if candidate and _is_installed(candidate):
            return candidate

    # Priority 2: explicit index match / fuzzy alias match.
    command = index.get(normalized) or fuzzy_match(normalized, index)
    if command and _is_installed(command):
        return command

    # Priority 3: direct command variants.
    candidates = [
        normalized,
        normalized.replace(" ", "-"),
        normalized.replace(" ", "_"),
    ]
    for candidate in candidates:
        if candidate and _is_installed(candidate):
            return candidate

    # Refresh scan once in case new apps were installed recently.
    refreshed = _get_installed_app_index(force_refresh=True)
    command = refreshed.get(normalized) or fuzzy_match(normalized, refreshed)
    if command and _is_installed(command):
        return command

    return None


def _allow_web_fallback(app_name: str) -> bool:
    """
    Prevent implicit social-web fallback when user asked to open native app.
    """
    normalized = _normalize_key(app_name)
    if normalized in {"music", "music player", "songs", "spotify", "youtube music"}:
        return True
    if normalized in NO_WEB_FALLBACK_APPS:
        return False
    return True


def preload_installed_apps_cache(force_refresh: bool = False) -> int:
    """
    Preload local installed app index and persist it for fast open_app lookups.
    """
    index = _get_installed_app_index(force_refresh=force_refresh)
    return len(index)


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

    # Special-case: direct YouTube search intent.
    # Example inputs: "youtube search for llm tutorial", "in youtube search for songs"
    if "youtube" in normalized_name and ("search" in normalized_name or " for " in normalized_name):
        query = normalized_name
        query = query.replace("in youtube", "").replace("on youtube", "")
        query = query.replace("youtube", "").replace("search for", "").replace("search", "").strip()
        if query:
            yt_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            try:
                logger.info(f"🌐 Opening YouTube search URL: {yt_url}")
                webbrowser.open(yt_url)
                return f"Opened YouTube search for '{query}' in your browser"
            except Exception as e:
                logger.error(f"Failed to open YouTube search URL: {e}")
                return f"Failed to open YouTube search: {e}"
    
    # 1. Strict local-first resolution (installed system apps win).
    command = _resolve_installed_command(normalized_name)

    # 2. Optional web fallback (only when allowed).
    web_url = fuzzy_match(normalized_name, WEB_MAP)
    if not command and web_url and _allow_web_fallback(normalized_name):
        try:
            logger.info(f"🌐 Opening web URL: {web_url}")
            webbrowser.open(web_url)
            return f"Opened {app_name} in your browser"
        except Exception as e:
            logger.error(f"Failed to open URL {web_url}: {e}")
            return f"Failed to open {app_name}: {e}"

    # 3. If no local command found, try raw command one final time.
    if not command:
        command = normalized_name
        logger.info(f"⚠️ No app mapping found, trying raw command: {command}")
    
    if not _is_installed(command):
        # For allowed destinations, fallback to web; otherwise force native-app failure.
        if web_url and _allow_web_fallback(normalized_name):
            try:
                logger.info(f"🌐 App missing, using web fallback: {web_url}")
                webbrowser.open(web_url)
                return f"Opened {app_name} in your browser"
            except Exception as e:
                logger.error(f"Failed to open web fallback URL {web_url}: {e}")
                return f"I couldn't open {app_name}. Command not found: {command}"
        logger.warning(f"❌ Command not found for app '{app_name}': {command}")
        return f"I couldn't open {app_name}. Command not found: {command}"

    try:
        subprocess.Popen(
            _split_command(command),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
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
    
    normalized_name = app_name.lower().strip()
    mapped = fuzzy_match(normalized_name, APP_MAP) or normalized_name
    target = _split_command(mapped)[0] if mapped else normalized_name

    try:
        subprocess.run(["pkill", "-f", target], check=True)
        return f"Closed {app_name}"
    except subprocess.CalledProcessError:
        return f"Could not find running process for {app_name}"
    except Exception as e:
        return f"Error closing {app_name}: {e}"

SHELL_UTILS = {
    "ls",
    "pwd",
    "cat",
    "grep",
    "find",
    "df",
    "du",
    "top",
    "htop",
    "ps",
    "kill",
    "echo",
    "which",
    "whereis",
    "uname",
    "whoami",
}


def _has_shell_operators(command: str) -> bool:
    markers = ("|", ">", "<", "&&", "||", ";")
    return any(marker in command for marker in markers)


def _single_word_token(command: str) -> Optional[str]:
    try:
        tokens = shlex.split(command)
    except Exception:
        return None
    if len(tokens) != 1:
        return None
    return tokens[0].strip()


def _should_detach_launch(command: str) -> bool:
    token = _single_word_token(command)
    if not token:
        return False
    if _has_shell_operators(command):
        return False
    if "/" in token:
        return False
    return token.lower() not in SHELL_UTILS

@function_tool(name="run_shell_command")
async def run_shell_command(context: RunContext, command: str) -> str:
    """
    Run a shell command on the local machine.
    
    Args:
        command: The shell command to execute (e.g., "ls -la", "uname -a").
    """
    logger.info(f"🐚 Executing shell command: {command}")
    try:
        if _should_detach_launch(command):
            subprocess.Popen(
                command,
                shell=True,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return "Launched successfully."

        # Non-GUI commands remain blocking with timeout and output capture.
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        return output.strip()
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after 30 seconds."
    except Exception as e:
        logger.error(f"Failed to execute command '{command}': {e}")
        return f"Error executing command: {e}"

@function_tool(name="set_volume")
async def set_volume(context: RunContext, percent: int) -> str:
    """
    Set system output volume percentage (0-100).

    Args:
        percent: Desired volume level from 0 to 100.
    """
    level = max(0, min(100, int(percent)))
    logger.info(f"🔊 Setting system volume to {level}%")
    try:
        if shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"], check=True)
            return f"Volume set to {level}%"
        if shutil.which("amixer"):
            subprocess.run(["amixer", "sset", "Master", f"{level}%"], check=True)
            return f"Volume set to {level}%"
        return "Could not set volume: no supported audio control command found (pactl/amixer)."
    except Exception as e:
        logger.error(f"Failed to set volume: {e}")
        return f"Failed to set volume: {e}"

@function_tool(name="take_screenshot")
async def take_screenshot(context: RunContext, filename: str = "") -> str:
    """
    Take a desktop screenshot and save it to ~/Pictures.

    Args:
        filename: Optional output filename ('.png' appended if missing).
    """
    base_dir = os.path.expanduser("~/Pictures")
    os.makedirs(base_dir, exist_ok=True)

    if filename:
        safe_name = filename if filename.endswith(".png") else f"{filename}.png"
    else:
        safe_name = f"maya_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    out_path = os.path.join(base_dir, safe_name)

    # Try common screenshot tools first.
    commands = []
    if shutil.which("gnome-screenshot"):
        commands.append(["gnome-screenshot", "-f", out_path])
    if shutil.which("scrot"):
        commands.append(["scrot", out_path])
    if shutil.which("import"):
        commands.append(["import", "-window", "root", out_path])

    for cmd in commands:
        try:
            subprocess.run(cmd, check=True, timeout=15)
            if os.path.exists(out_path):
                logger.info(f"📸 Screenshot saved: {out_path}")
                return f"Screenshot saved to {out_path}"
        except Exception:
            continue

    # Python fallback for environments without screenshot CLI tools.
    try:
        from mss import mss
        with mss() as sct:
            sct.shot(output=out_path)
        if os.path.exists(out_path):
            logger.info(f"📸 Screenshot saved via mss: {out_path}")
            return f"Screenshot saved to {out_path}"
    except Exception as e:
        logger.warning(f"mss screenshot fallback failed: {e}")

    return "Could not take screenshot: no supported screenshot utility found (gnome-screenshot/scrot/import/mss)."

@function_tool(name="file_write")
async def file_write(context: RunContext, path: str, content: str) -> str:
    """
    Write content to a file. Overwrites if exists.
    
    Args:
        path: Absolute or relative path to the file.
        content: The text content to write.
    """
    import os
    
    # Basic security check - prevent writing outside user home if possible, 
    # but for this agent we assume full control detailed in system prompt.
    # Expand user path
    full_path = os.path.expanduser(path)

    # Intelligent path correction: if path starts with / but isn't writable/doesn't exist as root,
    # try prepending user home. This fixes common LLM errors like "/Documents/file.txt"
    if full_path.startswith("/") and not os.path.exists(os.path.dirname(full_path)):
        # Check if the path relative to home exists
        home = os.path.expanduser("~")
        relative_path = full_path.lstrip("/")
        potential_path = os.path.join(home, relative_path)
        
        # If the parent directory of this potential path exists (e.g., ~/Documents exists), use it
        if os.path.exists(os.path.dirname(potential_path)):
            logger.info(f"🔄 Correcting path '{full_path}' to '{potential_path}'")
            full_path = potential_path
    
    logger.info(f"💾 Writing to file: {full_path}")
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return f"Successfully wrote to {full_path}"
    except Exception as e:
        logger.error(f"Failed to write file {path}: {e}")
        return f"Error writing file: {e}"
