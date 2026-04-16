import platform
import os
from pathlib import Path

def get_app_dir() -> Path:
    """Returns the base OS-specific application data directory for Sluice."""
    system = platform.system()
    home = Path.home()
    
    if system == "Windows":
        app_data = os.getenv("APPDATA", str(home / "AppData" / "Roaming"))
        return Path(app_data) / "Sluice"
    elif system == "Darwin":
        return home / "Library" / "Application Support" / "Sluice"
    else:
        # Linux/Unix standard
        xdg_data = os.getenv("XDG_DATA_HOME", str(home / ".local" / "share"))
        return Path(xdg_data) / "Sluice"

def get_config_dir() -> Path:
    """Directory for active json configurations."""
    p = get_app_dir() / "configs"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_torrents_dir() -> Path:
    """Directory for permanent ingested .torrent copies."""
    p = get_app_dir() / "torrents"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_resume_dir() -> Path:
    """Directory for the binary fastresume cache properties."""
    p = get_app_dir() / "resume"
    p.mkdir(parents=True, exist_ok=True)
    return p
