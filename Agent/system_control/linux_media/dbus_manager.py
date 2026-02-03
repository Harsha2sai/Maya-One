
import subprocess
import logging
import json
import re

logger = logging.getLogger(__name__)

class LinuxMediaManager:
    """
    Manages media playback on Linux using DBus/MPRIS2.
    Does NOT require `playerctl` - uses pure dbus-send.
    """
    
    MPRIS_PREFIX = "org.mpris.MediaPlayer2"
    MPRIS_PATH = "/org/mpris/MediaPlayer2"
    MPRIS_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
    DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"
    
    def _run_dbus(self, args):
        """Run a dbus-send command and return stdout"""
        cmd = ["dbus-send", "--print-reply"] + args
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.debug(f"DBus command failed: {' '.join(cmd)} | Error: {e.stderr}")
            return None
        except Exception as e:
            logger.error(f"Error executing DBus: {e}")
            return None

    def get_players(self):
        """List available MPRIS media players"""
        cmd = [
            "dbus-send", "--print-reply", 
            "--dest=org.freedesktop.DBus", 
            "/org/freedesktop/DBus", 
            "org.freedesktop.DBus.ListNames"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return []
                
            # Parse output for org.mpris.MediaPlayer2.*
            players = []
            for line in result.stdout.split('\n'):
                if "string" in line and self.MPRIS_PREFIX in line:
                    # Extract the name from quotes
                    match = re.search(r'"([^"]+)"', line)
                    if match:
                        name = match.group(1)
                        players.append(name)
            
            return players
        except Exception as e:
            logger.error(f"Error listing players: {e}")
            return []

    def get_active_player(self):
        """Find the first playing player, or fallback to first available"""
        players = self.get_players()
        if not players:
            return None
            
        # Try to find one that is playing
        for player in players:
            status = self.get_playback_status(player)
            if status == "Playing":
                return player
                
        # Fallback to first one (likely Spotify or browser)
        return players[0]

    def get_playback_status(self, dest):
        """Get PlaybackStatus (Playing, Paused, Stopped)"""
        args = [
            f"--dest={dest}",
            self.MPRIS_PATH,
            self.DBUS_PROPS_IFACE + ".Get",
            f"string:{self.MPRIS_PLAYER_IFACE}",
            "string:PlaybackStatus"
        ]
        
        output = self._run_dbus(args)
        if output and "string" in output:
            if "Playing" in output: return "Playing"
            if "Paused" in output: return "Paused"
            if "Stopped" in output: return "Stopped"
            
        return "Unknown"

    def get_metadata(self, dest=None):
        """Get metadata for the currently active player"""
        if not dest:
            dest = self.get_active_player()
            if not dest:
                return {"error": "No media player found"}
        
        args = [
            f"--dest={dest}",
            self.MPRIS_PATH,
            self.DBUS_PROPS_IFACE + ".Get",
            f"string:{self.MPRIS_PLAYER_IFACE}",
            "string:Metadata"
        ]
        
        output = self._run_dbus(args)
        if not output:
            return {"error": "Failed to fetch metadata"}
            
        # Simple extraction using regex
        metadata = {}
        
        # Extract title
        title_match = re.search(r'xesam:title"\s+variant\s+string\s+"([^"]+)"', output)
        if title_match:
            metadata['title'] = title_match.group(1)
            
        # Extract artist (array or string)
        artist_match = re.search(r'xesam:artist"\s+variant\s+array\s+\[\s+string\s+"([^"]+)"', output)
        if artist_match:
            metadata['artist'] = artist_match.group(1)
            
        # Extract album
        album_match = re.search(r'xesam:album"\s+variant\s+string\s+"([^"]+)"', output)
        if album_match:
            metadata['album'] = album_match.group(1)
            
        return metadata

    def control(self, command):
        """
        Execute control command: play, pause, play_pause, next, previous
        """
        player = self.get_active_player()
        if not player:
            return "No media player found running on system."
            
        dbus_method = ""
        if command == "play": dbus_method = "Play"
        elif command == "pause": dbus_method = "Pause"
        elif command == "play_pause": dbus_method = "PlayPause"
        elif command == "next": dbus_method = "Next"
        elif command == "previous": dbus_method = "Previous"
        else:
            return f"Unknown command: {command}"
            
        args = [
            f"--dest={player}",
            self.MPRIS_PATH,
            f"{self.MPRIS_PLAYER_IFACE}.{dbus_method}"
        ]
        
        result = self._run_dbus(args)
        
        # Verify result by checking status or metadata
        if command in ["next", "previous"]:
            meta = self.get_metadata(player)
            song = meta.get('title', 'Unknown Track')
            artist = meta.get('artist', 'Unknown Artist')
            return f"{command.capitalize()} successful. Now playing: {song} by {artist}"
            
        status = self.get_playback_status(player)
        return f"Command '{command}' sent. Status: {status}"

