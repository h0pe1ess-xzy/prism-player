import json
import os

SETTINGS_DIR = os.path.expanduser("~/.musicbeast")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "cava_enabled": True,
    "default_volume": 50,
    "history_limit": 50,
    "theme": "Cyberpunk",
    "discord_rpc_enabled": False,
    "eq_bass": 0,
    "eq_treble": 0,
    "soundcloud_token": "",
    "notifications_enabled": True,
    "audio_fx": "Normal"
}

def _ensure_dir():
    os.makedirs(SETTINGS_DIR, exist_ok=True)

def load_settings():
    _ensure_dir()
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            settings = DEFAULT_SETTINGS.copy()
            settings.update(data)
            return settings
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings_obj=None):
    _ensure_dir()
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings_obj or settings, f, indent=2)
    except Exception:
        pass

settings = load_settings()
CACHE_DIR = "/tmp/prism_player_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def safe_cache_id(item_id):
    if not item_id: return "unknown"
    import hashlib
    s = str(item_id)
    if "://" in s or "/" in s:
        return hashlib.md5(s.encode()).hexdigest()
    return "".join(c for c in s if c.isalnum() or c in "-_")
