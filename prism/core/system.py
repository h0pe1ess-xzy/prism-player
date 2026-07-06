import os
import subprocess
import re
from prism.core.config import settings

def get_system_volume():
    try:
        out = subprocess.check_output(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], stderr=subprocess.DEVNULL).decode()
        match = re.search(r"(\d+)%", out)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    try:
        out = subprocess.check_output(["amixer", "sget", "Master"], stderr=subprocess.DEVNULL).decode()
        match = re.search(r"\[(\d+)%\]", out)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return 100

def set_system_volume(volume_percent):
    try:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume_percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["amixer", "set", "Master", f"{volume_percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def notify_track(info):
    if not settings.get("notifications_enabled", True): return
    try:
        t = info.get("title", "Unknown")
        a = info.get("artists", [{"name": "Unknown"}])[0]["name"] if info.get("artists") else info.get("author", "Unknown")
        subprocess.Popen(["notify-send", "-a", "Prism Player", f"🎵 {t}", f"by {a}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

