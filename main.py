from prism.core.themes import THEMES
from prism.core.system import get_system_volume, set_system_volume, notify_track
from prism.graphics import generate_ansi_art, generate_mini_art, download_cover_to_cache, get_cava_color, generate_smooth_cava_horizontal
from prism.ui.components import generate_app_header, draw_mini_soundbar, render_card
from prism.ui.views import draw_home_dashboard, draw_search_view, draw_player_view, draw_settings_view, draw_playlists_view, draw_lyrics_popup, draw_eq_popup, draw_popup

import sys
import os

import subprocess
import time
import threading
import re
import math
import random
import signal
import json
import base64
from io import BytesIO
import requests
from PIL import Image

from rich.live import Live
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.text import Text
from rich.progress_bar import ProgressBar
from rich.panel import Panel
from rich.table import Table
from blessed import Terminal
from prism.api.aggregator import search_all, get_dashboard_sections, get_stream_info, yt_client, refresh_yt_client, get_youtube_playlists, get_lyrics
from prism.core.config import settings, save_settings, CACHE_DIR, safe_cache_id
from prism.core.history import add_to_history, get_history
from prism.core.playlists import get_all_playlists, create_playlist, delete_playlist, add_track, remove_track, get_tracks


from rich.theme import Theme
console = Console(theme=THEMES["Cyberpunk"])

os.makedirs(CACHE_DIR, exist_ok=True)

# Auth is now handled in aggregator.py

# --- ГЛОБАЛЬНІ СТАНИ ---
FPS = 15
cava_states = {"left": [], "right": []}
cava_enabled = settings.get("cava_enabled", True)
current_volume = settings.get("default_volume", 50)
theme_name = settings.get("theme", "Cyberpunk")
if theme_name in THEMES:
    console.push_theme(THEMES[theme_name])
home_data = []  # Дані для дашборду
home_loading = True
mini_art_cache = {}  # Кеш мініатюрних обкладинок {video_id: Text}
dashboard_covers_ready = threading.Event()
toast_message = ""  # Тост-повідомлення
toast_time = 0  # Час показу тосту

# --- ФОНОВЕ ЗАВАНТАЖЕННЯ ДАШБОРДУ ---
def fetch_home_dashboard():
    global home_data, home_loading
    try:
        sections = get_dashboard_sections()
        parsed = []
        history_items = get_history(limit=20)
        if history_items:
            hist_row = {
                "title": "♻ Recently Played",
                "items": [{
                    "title": h.get("title", "Unknown"),
                    "artist": h.get("artist", "Unknown"),
                    "id": h.get("id", h.get("videoId")),
                    "source": h.get("source", "youtube"),
                    "thumbnails": h.get("thumbnails", [])
                } for h in history_items]
            }
            parsed.append(hist_row)
        parsed.extend(sections)
        home_data = parsed
    except Exception:
        pass
    home_loading = False

    # Фонове завантаження обкладинок для дашборду
    threading.Thread(target=preload_dashboard_covers, daemon=True).start()


def preload_dashboard_covers():
    """Завантажує обкладинки для всіх елементів дашборду у фоні."""
    for section in home_data:
        for item in section.get("items", []):
            item_id = item.get("id") or item.get("videoId") or item.get("playlistId") or item.get("browseId")
            if item_id:
                cache_path = os.path.join(CACHE_DIR, f"{safe_cache_id(item_id)}.png")
                if not os.path.exists(cache_path):
                    download_cover_to_cache(item_id, item.get("thumbnails", []))
    dashboard_covers_ready.set()


# Запускаємо вантаження дашборду паралельно з запуском UI
threading.Thread(target=fetch_home_dashboard, daemon=True).start()

# --- СИНХРОНІЗАЦІЯ З СИСТЕМНОЮ ГУЧНІСТЮ ---


# --- РЕНДЕРИНГ ОБКЛАДИНКИ ---







def render_card(item, is_active, card_width=24):
    """Рендерить одну карточку дашборду як Panel з мініатюрою."""
    art_w = card_width - 4  # Враховуємо padding і borders панелі
    item_id = item.get("id") or item.get("videoId") or item.get("playlistId") or item.get("browseId")
    mini_art = generate_mini_art(
        item_id,
        item.get("thumbnails"),
        width=art_w,
        height=10
    )

    title = item.get("title", "Unknown")
    artist = item.get("artist", "Unknown")
    if len(title) > art_w:
        title = title[:art_w - 2] + ".."
    if len(artist) > art_w:
        artist = artist[:art_w - 2] + ".."

    card_content = Group(
        mini_art,
        Text(title, style="bold white", no_wrap=True, overflow="ellipsis"),
        Text(artist, style="primary.dim", no_wrap=True, overflow="ellipsis")
    )

    border_style = "primary.bold" if is_active else "grey23"
    title_style = "secondary.bold" if is_active else ""

    return Panel(
        card_content,
        width=card_width,
        border_style=border_style,
        title="▶" if is_active else None,
        title_align="center",
        style=title_style
    )


# --- ПЛАВНИЙ ВІЗУАЛІЗАТОР CAVA ---


# --- ANTI-LAG BACKGROUND PRELOADER ---
preloaded_track_data = None
preloading_in_progress = False

def preload_next_track_worker(track_dict, width):
    global preloaded_track_data, preloading_in_progress
    preloading_in_progress = True
    try:
        track_id = track_dict.get("id", track_dict.get("videoId"))
        source = track_dict.get("source", "youtube")
        
        song_info = {
            "title": track_dict.get("title", "Unknown"),
            "artists": [{"name": track_dict.get("artist", "Unknown")}],
            "thumbnails": track_dict.get("thumbnails", []),
            "source": source
        }

        stream_link, duration = get_stream_info(track_id, source, song_info["title"], song_info["artists"][0]["name"])
        song_info["duration_seconds"] = duration
        
        download_cover_to_cache(track_id, song_info.get("thumbnails"))
        art_panel = generate_ansi_art(track_id, song_info.get("thumbnails"), width=width)
        
        autoplay_queue = []
        try:
            if source == "youtube":
                fallback = yt_client.search(song_info.get("title", ""), limit=15)
                for t in fallback:
                    if t.get("videoId") and t.get("videoId") != track_id:
                        autoplay_queue.append({
                            "id": t.get("videoId"),
                            "title": t.get("title"),
                            "artist": t.get("artists", [{"name": "Unknown"}])[0]["name"] if t.get("artists") else "Unknown",
                            "source": "youtube",
                            "thumbnails": t.get("thumbnails", [])
                        })
            elif source == "soundcloud":
                from prism.api.aggregator import search_soundcloud
                fallback = search_soundcloud(f"{song_info.get('title', '')} {song_info['artists'][0]['name']}", limit=15)
                for t in fallback:
                    if t.get("id") and t.get("id") != track_id:
                        autoplay_queue.append(t)
            elif source == "spotify":
                from prism.api.aggregator import search_spotify
                fallback = search_spotify(f"{song_info.get('title', '')} {song_info['artists'][0]['name']}", limit=15)
                for t in fallback:
                    if t.get("id") and t.get("id") != track_id:
                        autoplay_queue.append(t)
        except Exception:
            pass
                
        preloaded_track_data = {
            "track_id": track_id,
            "song_info": song_info,
            "art_panel": art_panel,
            "stream_link": stream_link,
            "autoplay_queue": autoplay_queue
        }
    except Exception:
        preloaded_track_data = None
    preloading_in_progress = False

def trigger_next_track_preload(track_dict, width):
    global preloaded_track_data
    preloaded_track_data = None
    t = threading.Thread(target=preload_next_track_worker, args=(track_dict, width), daemon=True)
    t.start()


# --- UI LAYOUT GENERATORS ---

# --- SHARED HEADER ---



# --- SETTINGS VIEW ---

# --- PLAYLISTS VIEW ---


# --- LYRICS POPUP ---


# --- SEARCH & DASHBOARD VIEWS ---






# --- CORE FFPLAY LAUNCHER ENGINE ---
def start_track(track_dict, start_seconds=0):
    track_id = track_dict.get("id", track_dict.get("videoId"))
    source = track_dict.get("source", "youtube")
    
    song_info = {
        "title": track_dict.get("title", "Unknown"),
        "artists": [{"name": track_dict.get("artist", "Unknown")}],
        "thumbnails": track_dict.get("thumbnails", []),
        "source": source
    }

    song_info["duration_seconds"] = 1 # temporary until fetched
    proc = None
    
    target_path = os.path.join(CACHE_DIR, f"{safe_cache_id(track_id)}.png")
    if os.path.exists(target_path):
        art_panel = generate_ansi_art(track_id, song_info.get("thumbnails"), width=46)
    else:
        art_panel = Text("\n[ Loading Artwork... ]\n", style="dim grey50")
        def fetch_art_bg():
            import time
            time.sleep(0.1) # Wait for main thread to assign video_id
            try:
                if not os.path.exists(target_path):
                    download_cover_to_cache(track_id, song_info.get("thumbnails"))
                if globals().get("video_id") == track_id:
                    globals()["art_panel"] = generate_ansi_art(track_id, song_info.get("thumbnails"), width=46)
            except Exception:
                pass
        import threading
        threading.Thread(target=fetch_art_bg, daemon=True).start()
    
    def ffplay_launch_bg():
        try:
            stream_link, duration = get_stream_info(track_id, source, song_info["title"], song_info["artists"][0]["name"])
            if globals().get("video_id") != track_id:
                return # Track changed before load
            
            song_info["duration_seconds"] = duration
            globals()["total_duration"] = int(duration)
            
            bass = settings.get("eq_bass", 0)
            treble = settings.get("eq_treble", 0)
            af_filter = f"bass=g={bass},treble=g={treble}"
            
            fx = settings.get("audio_fx", "Normal")
            if fx == "Nightcore":
                af_filter += ",atempo=1.2,asetrate=44100*1.2,aresample=44100"
            elif fx == "Slowed":
                af_filter += ",atempo=0.85,asetrate=44100*0.85,aresample=44100,aecho=0.8:0.88:60:0.4"

            ffplay_cmd = [
                "ffplay", "-nodisp", "-autoexit",
                "-ss", str(start_seconds),
                "-af", af_filter,
                "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                stream_link
            ]
            if globals().get("video_id") == track_id:
                globals()["start_time"] = __import__('time').time() - start_seconds
                p = subprocess.Popen(ffplay_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                globals()["process"] = p
                if start_seconds == 0:
                    notify_track(song_info)
            else:
                p.kill()
        except Exception:
            pass
            
    import threading
    threading.Thread(target=ffplay_launch_bg, daemon=True).start()

    autoplay_queue = []
    def fetch_autoplay_bg():
        try:
            from prism.api.aggregator import yt_client, search_youtube
            
            actual_vid = track_id
            if source != "youtube":
                query = f"{song_info.get('title', '')} {song_info['artists'][0]['name']}"
                yt_res = search_youtube(query, limit=1)
                if yt_res:
                    actual_vid = yt_res[0]["id"]

            try:
                radio = yt_client.get_watch_playlist(videoId=actual_vid)
                fallback = radio.get("tracks", [])
            except Exception:
                fallback = yt_client.search(song_info.get("title", ""), limit=10)
            
            auto_q = []
            for t in fallback:
                if t.get("videoId") and t.get("videoId") != track_id and t.get("videoId") != actual_vid:
                    auto_q.append({
                        "id": t.get("videoId"),
                        "title": t.get("title"),
                        "artist": t.get("artists", [{"name": "Unknown"}])[0]["name"] if t.get("artists") else "Unknown",
                        "source": "youtube",
                        "thumbnails": t.get("thumbnails", [])
                    })
            
            # Set globals if not populated yet (e.g. not playing from a playlist)
            if not globals().get("autoplay_tracks"):
                globals()["autoplay_tracks"] = auto_q
        except Exception:
            pass
    import threading
    threading.Thread(target=fetch_autoplay_bg, daemon=True).start()

    return song_info, art_panel, proc, autoplay_queue


# --- MAIN APPLICATION LOOP ---
if __name__ == "__main__":
    term = Terminal()

    current_mode = "HOME"  # Починаємо з Дашборду
    # cava_enabled reads from config

    # Стейт для Home
    home_row_idx = 0
    home_col_idx = 0

    search_query = ""
    search_results = []
    selected_result_idx = 0
    search_page = 0
    ITEMS_PER_PAGE = 7
    is_repeating = False

    # Стейт налаштувань
    settings_idx = 0

    # Стейт плейлістів
    cached_all_pls = get_all_playlists()
    yt_playlists_cache = None
    yt_playlists_loading = False

    def refresh_local_playlists():
        global cached_all_pls
        cached_all_pls = get_all_playlists()

    def fetch_remote_playlists_worker():
        global yt_playlists_cache, yt_playlists_loading
        yt_playlists_loading = True
        try:
            from prism.api.aggregator import get_spotify_playlists, get_soundcloud_playlists
            res = get_youtube_playlists()
            res.extend(get_spotify_playlists())
            res.extend(get_soundcloud_playlists())
            yt_playlists_cache = res
        except Exception:
            yt_playlists_cache = []
        yt_playlists_loading = False
    pl_list_idx = 0
    pl_track_idx = 0
    pl_focus = "list"  # "list" або "tracks"

    # Стейт попапів
    popup_mode = None  # None, "ADD_TO_PLAYLIST", "CREATE_PLAYLIST", "LYRICS"
    popup_idx = 0
    popup_text = ""
    current_lyrics = None
    lyrics_scroll = 0

    song_info = {"title": "No Track Loaded", "artists": [{"name": "Press '/' to search"}]}
    video_id = ""
    art_panel = generate_ansi_art("", [], width=46)
    autoplay_tracks = []
    history_tracks = []
    process = None

    # current_volume is set from config globally
    start_time = time.time()
    total_duration = 1
    is_paused = False
    paused_time_accumulated = 0
    pause_start_mark = 0

    # Ініціалізація глобальних змінних стану для потоків
    elapsed = 0

    def discord_rpc_loop():
        import time
        try:
            import discord_rpc
        except Exception:
            return
        while True:
            try:
                if settings.get("discord_rpc_enabled", False):
                    title = song_info.get("title", "No Track Loaded")
                    if title != "No Track Loaded" and process:
                        artist = "Unknown"
                        if song_info.get("artists"): artist = song_info["artists"][0]["name"]
                        elif song_info.get("author"): artist = song_info["author"]
                        
                        # Fix for pause sync: only send real elapsed if not paused, else we could send a static timestamp
                        el = elapsed
                        discord_rpc.update_presence(title, artist, el)
                    else:
                        discord_rpc.clear_presence()
                else:
                    discord_rpc.clear_presence()
            except Exception:
                pass
            time.sleep(5)

    threading.Thread(target=discord_rpc_loop, daemon=True).start()

    def get_mpris_state():
        artist_name = "Unknown"
        if song_info.get("artists"): artist_name = song_info["artists"][0]["name"]
        elif song_info.get("author"): artist_name = song_info["author"]
        return {
            "is_paused": is_paused,
            "is_playing": process is not None and process.poll() is None,
            "video_id": video_id,
            "title": song_info.get("title", "No Track Loaded"),
            "artist": artist_name,
            "duration": total_duration,
            "elapsed": elapsed
        }
    
    try:
        from mpris import run_mpris_background, mpris_command_queue
        run_mpris_background(get_mpris_state)
    except Exception:
        pass

    try:
        with term.cbreak(), term.hidden_cursor(), Live(draw_home_dashboard(0, 0, term.width, term.height, draw_mini_soundbar(song_data=song_info, elapsed=0, total_duration=1, is_paused=False, term_width=term.width), home_loading, home_data, toast_message, toast_time), console=console, screen=True, refresh_per_second=FPS) as live:
            while True:
                if toast_message and (time.time() - toast_time) >= 2.5:
                    toast_message = ""
                tw = term.width
                th = term.height

                try:
                    from mpris import mpris_command_queue
                    while mpris_command_queue:
                        cmd = mpris_command_queue.popleft()
                        if cmd == "pause" and not is_paused and process:
                            os.kill(process.pid, signal.SIGSTOP)
                            is_paused = True
                            pause_start_mark = time.time()
                        elif cmd == "play" and is_paused and process:
                            os.kill(process.pid, signal.SIGCONT)
                            is_paused = False
                            paused_time_accumulated += (time.time() - pause_start_mark)
                        elif cmd == "next" and autoplay_tracks:
                            process.kill() # Trigger next track logic
                        elif cmd == "previous" and history_tracks:
                            # Implemented simple previous trigger
                            prev = history_tracks.pop()
                            video_id = prev["video_id"]
                            song_info = prev["info"]
                            art_panel = prev["art"]
                            process.kill()
                            from prism.api.aggregator import yt_client
                            try:
                                radio = yt_client.get_watch_playlist(videoId=video_id)
                                fallback = radio.get("tracks", [])
                                auto_q = []
                                for t in fallback:
                                    if t.get("videoId") and t.get("videoId") != video_id:
                                        auto_q.append({
                                            "id": t["videoId"],
                                            "title": t.get("title", "Unknown"),
                                            "artist": ", ".join(a["name"] for a in t.get("artists", [])) if t.get("artists") else "Unknown",
                                            "thumbnails": t.get("thumbnail", []),
                                            "source": "youtube"
                                        })
                                autoplay_tracks = auto_q
                            except Exception:
                                pass
                            song_info, art_panel, process, _ = start_track({"id": video_id, "title": song_info.get("title"), "artist": song_info.get("artists", [{"name": "Unknown"}])[0]["name"], "source": song_info.get("source", "youtube"), "thumbnails": song_info.get("thumbnails")})
                            start_time = time.time()
                            paused_time_accumulated = 0
                except Exception:
                    pass

                # Обрахунок часу програвання
                if process and process.poll() is None:
                    if not is_paused:
                        elapsed = int(time.time() - start_time - paused_time_accumulated)
                    else:
                        elapsed = int(pause_start_mark - start_time - paused_time_accumulated)
                    if elapsed > total_duration:
                        elapsed = total_duration

                    if total_duration - elapsed <= 15 and autoplay_tracks and not preloading_in_progress and not preloaded_track_data:
                        trigger_next_track_preload(autoplay_tracks[0], width=min(46, tw - 10))
                else:
                    elapsed = 0
                    if process and not is_paused and (autoplay_tracks or preloaded_track_data):
                        history_tracks.append({"video_id": video_id, "info": song_info, "art": art_panel})

                        if preloaded_track_data and autoplay_tracks and preloaded_track_data.get("track_id") == autoplay_tracks[0].get("id", autoplay_tracks[0].get("videoId")):
                            data = preloaded_track_data
                            video_id = data["track_id"]
                            song_info = data["song_info"]
                            art_panel = data["art_panel"]
                            autoplay_tracks = data["autoplay_queue"]

                            bass = settings.get("eq_bass", 0)
                            treble = settings.get("eq_treble", 0)
                            af_filter = f"bass=g={bass},treble=g={treble}"
                            process = subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-af", af_filter, "-reconnect", "1", "-reconnect_streamed", "1", data["stream_link"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            start_time = time.time()
                            paused_time_accumulated = 0
                            total_duration = int(song_info["duration_seconds"])
                            preloaded_track_data = None
                        elif autoplay_tracks:
                            if is_repeating:
                                # Start the exact same track
                                try:
                                    # re-use existing song_info, video_id stays same
                                    _, _, process, _ = start_track({"id": video_id, "title": song_info.get("title"), "artist": song_info["artists"][0]["name"], "source": song_info.get("source", "youtube"), "thumbnails": song_info.get("thumbnails")})
                                    start_time = time.time()
                                    paused_time_accumulated = 0
                                except Exception:
                                    process = None
                            else:
                                next_track = autoplay_tracks.pop(0)
                                video_id = next_track.get("id", next_track.get("videoId"))
                                try:
                                    song_info, art_panel, process, new_auto = start_track(next_track)
                                    if not autoplay_tracks:
                                        autoplay_tracks = new_auto
                                    start_time = time.time()
                                    paused_time_accumulated = 0
                                    total_duration = int(song_info["duration_seconds"])
                                except Exception:
                                    process = None

                next_title = autoplay_tracks[0].get("title", "Loading radio...") if autoplay_tracks else "End of Queue"
                mini_player = draw_mini_soundbar(song_info, elapsed, total_duration, is_paused, tw)

                # Рендер UI залежно від режиму
                if popup_mode:
                    # Попап поверх всього
                    all_pls = get_all_playlists()
                    if popup_mode == "ADD_TO_PLAYLIST":
                        # Only show local playlists for adding
                        items = [f"{p['name']}  ({len(p.get('tracks',[]))})" for p in cached_all_pls]
                        items.append("── ✚ New Playlist ──")
                        live.update(draw_popup(
                            "Add to Playlist", items, popup_idx, tw, th, mini_player,
                            footer_hint="[Enter] Add │ [Esc] Cancel"
                        ))
                    elif popup_mode == "CREATE_PLAYLIST":
                        live.update(draw_popup(
                            "Create New Playlist", [], 0, tw, th, mini_player,
                            input_mode=True, input_text=popup_text,
                            footer_hint="[Enter] Create │ [Esc] Cancel"
                        ))
                    elif popup_mode == "YT_LOGIN":
                        msg = "Please paste your Cookie string from music.youtube.com.\n  (Open DevTools -> Network -> Headers -> Cookie)"
                        live.update(draw_popup(
                            "Linked Accounts", [], 0, tw, th, mini_player,
                            input_mode=True, input_text=popup_text, message=msg,
                            footer_hint="[Enter] Save │ [Esc] Cancel"
                        ))
                    elif popup_mode == "SC_LOGIN":
                        msg = "Please paste your SoundCloud OAuth Token.\n  (Open DevTools -> Application -> Cookies -> oauth_token)"
                        live.update(draw_popup(
                            "SoundCloud Login", [], 0, tw, th, mini_player,
                            input_mode=True, input_text=popup_text, message=msg,
                            footer_hint="[Enter] Save │ [Esc] Cancel"
                        ))
                    elif popup_mode == "LYRICS":
                        live.update(draw_lyrics_popup(current_lyrics, lyrics_scroll, elapsed, tw, th, mini_player))
                    elif popup_mode == "EQ":
                        live.update(draw_eq_popup(settings, popup_idx, tw, th, mini_player))
                elif current_mode == "PLAYER":
                    live.update(draw_player_view(song_info, art_panel, elapsed, total_duration, current_volume, is_paused, next_title, term_width=tw, term_height=th, cava_enabled=cava_enabled))
                elif current_mode == "HOME":
                    live.update(draw_home_dashboard(home_row_idx, home_col_idx, tw, th, mini_player, home_loading, home_data, toast_message, toast_time))
                elif current_mode == "MINI":
                    mini_layout = Layout()
                    header = Text("\n   ◆ PRISM PLAYER (Mini Mode) ◆\n", style="primary.bold", justify="center")
                    hints = Text("\n[M/Tab] Fullscreen │ [Space] Pause │ [↔] Skip 5s │ [Q] Exit", style="dim grey50", justify="center")
                    mini_layout.split_column(
                        Layout(Align.center(header), name="head", ratio=1),
                        Layout(mini_player, name="foot", size=4),
                        Layout(Align.center(hints), name="hints", size=2)
                    )
                    blank_space = Text("\n" * max(0, th - 8))
                    mini_layout["head"].update(Align.center(Group(header, blank_space)))
                    live.update(mini_layout)
                elif current_mode == "SEARCH":
                    live.update(draw_search_view(search_query, search_results, selected_result_idx, search_page, ITEMS_PER_PAGE, tw, mini_player))
                elif current_mode == "SETTINGS":
                    live.update(draw_settings_view(settings, settings_idx, tw, th, mini_player))
                elif current_mode == "PLAYLISTS":
                    all_pls = list(cached_all_pls)
                    yt_cache = globals().get("yt_playlists_cache")
                    if yt_cache is not None:
                        all_pls.extend(yt_cache)
                    elif globals().get("yt_playlists_loading"):
                        all_pls.append({"id": "loading", "name": "Loading Linked Playlists...", "tracks": [], "is_youtube": True})
                    live.update(draw_playlists_view(all_pls, pl_list_idx, pl_track_idx, pl_focus, tw, th, mini_player))

                key = term.inkey(timeout=1.0 / FPS)
                if not key:
                    continue

                # ═══ ПОПАП ОБРОБКА (пріоритет над усім) ═══
                if popup_mode:
                    if popup_mode == "ADD_TO_PLAYLIST":
                        all_pls = get_all_playlists()
                        max_items = len(all_pls) + 1  # +1 для "New Playlist"
                        if key.name == "KEY_DOWN":
                            popup_idx = (popup_idx + 1) % max_items
                        elif key.name == "KEY_UP":
                            popup_idx = (popup_idx - 1) % max_items
                        elif key.name == "KEY_ENTER":
                            if popup_idx < len(all_pls):
                                # Додаємо трек в існуючий плейліст
                                pl = all_pls[popup_idx]
                                artist_name = "Unknown"
                                if song_info.get("artists"): artist_name = song_info["artists"][0]["name"]
                                elif song_info.get("author"): artist_name = song_info["author"]
                                ok = add_track(pl["id"], video_id, song_info.get("title", "Unknown"), artist_name, song_info.get("source", "youtube"), song_info.get("thumbnails"))
                                toast_message = f"Added to '{pl['name']}'" if ok else f"Already in '{pl['name']}'"
                                toast_time = time.time()
                                popup_mode = None
                            else:
                                # Створити новий плейліст
                                popup_mode = "CREATE_PLAYLIST"
                                popup_text = ""
                        elif key.name == "KEY_ESCAPE":
                            popup_mode = None

                    elif popup_mode == "CREATE_PLAYLIST":
                        if key.name == "KEY_ENTER" and popup_text.strip():
                            new_pl = create_playlist(popup_text.strip())
                            # Якщо є трек що грає — додаємо його
                            if video_id and song_info.get("title") != "No Track Loaded":
                                artist_name = "Unknown"
                                if song_info.get("artists"): artist_name = song_info["artists"][0]["name"]
                                elif song_info.get("author"): artist_name = song_info["author"]
                                add_track(new_pl["id"], video_id, song_info.get("title", "Unknown"), artist_name, song_info.get("source", "youtube"), song_info.get("thumbnails"))
                                toast_message = f"Created '{popup_text.strip()}' + added track"
                            else:
                                toast_message = f"Created '{popup_text.strip()}'"
                            toast_time = time.time()
                            popup_mode = None
                        elif key.name == "KEY_ESCAPE":
                            popup_mode = None
                        elif key.name == "KEY_BACKSPACE":
                            popup_text = popup_text[:-1]
                        elif not key.is_sequence and len(popup_text) < 40:
                            popup_text += key

                    elif popup_mode == "YT_LOGIN":
                        if key.name == "KEY_ENTER":
                            if popup_text.strip():
                                auth_path = os.path.expanduser("~/.musicbeast/headers_auth.json")
                                import json
                                try:
                                    # Minimal YTMusic headers format
                                    headers = {
                                        "cookie": popup_text.strip(),
                                        "x-goog-authuser": "0",
                                        "authorization": "SAPISIDHASH fake",
                                        "origin": "https://music.youtube.com"
                                    }
                                    with open(auth_path, "w") as f:
                                        json.dump(headers, f)
                                    refresh_yt_client()
                                    globals()["yt_playlists_cache"] = None
                                    threading.Thread(target=fetch_home_dashboard, daemon=True).start()
                                    toast_message = "Logged in successfully!"
                                except Exception:
                                    toast_message = "Failed to save login"
                                toast_time = time.time()
                            popup_mode = None
                        elif key.name == "KEY_ESCAPE":
                            popup_mode = None
                        elif key.name == "KEY_BACKSPACE":
                            popup_text = popup_text[:-1]
                        elif not key.is_sequence:
                            popup_text += key

                    elif popup_mode == "SC_LOGIN":
                        if key.name == "KEY_ENTER":
                            if popup_text.strip():
                                settings["soundcloud_token"] = popup_text.strip()
                                save_settings(settings)
                                globals()["yt_playlists_cache"] = None
                                toast_message = "SoundCloud Token Saved!"
                                toast_time = time.time()
                            popup_mode = None
                        elif key.name == "KEY_ESCAPE":
                            popup_mode = None
                        elif key.name == "KEY_BACKSPACE":
                            popup_text = popup_text[:-1]
                        elif not key.is_sequence:
                            popup_text += key

                    elif popup_mode == "LYRICS":
                        if key.name == "KEY_ESCAPE" or key.lower() == "l":
                            popup_mode = None
                        elif key.name == "KEY_DOWN":
                            lyrics_scroll += 1
                        elif key.name == "KEY_UP":
                            lyrics_scroll = max(0, lyrics_scroll - 1)

                    elif popup_mode == "EQ":
                        if key.name == "KEY_ESCAPE" or key.lower() == "e":
                            popup_mode = None
                        elif key.name == "KEY_DOWN":
                            popup_idx = min(2, popup_idx + 1)
                        elif key.name == "KEY_UP":
                            popup_idx = max(0, popup_idx - 1)
                        elif key.name == "KEY_LEFT":
                            if popup_idx == 0: settings["eq_bass"] = max(-10, settings.get("eq_bass", 0) - 1)
                            elif popup_idx == 1: settings["eq_treble"] = max(-10, settings.get("eq_treble", 0) - 1)
                            elif popup_idx == 2:
                                fxs = ["Normal", "Nightcore", "Slowed"]
                                cur_fx = settings.get("audio_fx", "Normal")
                                settings["audio_fx"] = fxs[(fxs.index(cur_fx) - 1) % 3]
                            save_settings(settings)
                        elif key.name == "KEY_RIGHT":
                            if popup_idx == 0: settings["eq_bass"] = min(10, settings.get("eq_bass", 0) + 1)
                            elif popup_idx == 1: settings["eq_treble"] = min(10, settings.get("eq_treble", 0) + 1)
                            elif popup_idx == 2:
                                fxs = ["Normal", "Nightcore", "Slowed"]
                                cur_fx = settings.get("audio_fx", "Normal")
                                settings["audio_fx"] = fxs[(fxs.index(cur_fx) + 1) % 3]
                            save_settings(settings)

                    continue

                # ═══ ГЛОБАЛЬНІ КЛАВІШІ ═══
                if key.lower() == "q" and current_mode != "SEARCH":
                    break

                if key.lower() == "r" and current_mode == "PLAYER":
                    is_repeating = not is_repeating
                    toast_message = f"Repeat: {'ON' if is_repeating else 'OFF'}"
                    toast_time = time.time()
                    continue

                if key.lower() == "e" and current_mode == "PLAYER":
                    popup_mode = "EQ"
                    popup_idx = 0
                    continue

                if key.lower() == "l" and current_mode == "PLAYER":
                    popup_mode = "LYRICS"
                    current_lyrics = None
                    lyrics_scroll = 0
                    def fetch_lyrics_bg():
                        try:
                            t = song_info.get("title", "")
                            a = "Unknown"
                            if song_info.get("artists"): a = song_info["artists"][0]["name"]
                            elif song_info.get("author"): a = song_info["author"]
                            globals()["current_lyrics"] = get_lyrics(t, a)
                        except Exception:
                            globals()["current_lyrics"] = {"type": "error", "text": "Failed to load lyrics."}
                    threading.Thread(target=fetch_lyrics_bg, daemon=True).start()
                    continue

                if key.lower() == "s" and current_mode != "SEARCH":
                    current_mode = "SETTINGS"
                    settings_idx = 0
                    continue

                if key.name == "KEY_TAB":
                    if current_mode == "PLAYER":
                        current_mode = "HOME"
                    elif current_mode == "PLAYLISTS":
                        current_mode = "HOME"
                    elif current_mode == "MINI":
                        current_mode = "PLAYER"
                    else:
                        current_mode = "PLAYER"
                    continue

                if key.lower() == "m" and current_mode != "SEARCH":
                    if current_mode != "MINI":
                        globals()["previous_mode"] = current_mode
                        current_mode = "MINI"
                    else:
                        current_mode = globals().get("previous_mode", "PLAYER")
                    continue

                if key == "/" and current_mode != "SEARCH":
                    current_mode = "SEARCH"
                    search_query = ""
                    search_results = []
                    selected_result_idx = 0
                    search_page = 0
                    continue

                if key.lower() == "p" and current_mode != "SEARCH":
                    current_mode = "PLAYLISTS"
                    pl_list_idx = 0
                    pl_track_idx = 0
                    pl_focus = "list"
                    refresh_local_playlists()
                    if globals().get("yt_playlists_cache") is None and not globals().get("yt_playlists_loading"):
                        threading.Thread(target=fetch_remote_playlists_worker, daemon=True).start()
                    continue

                if key.lower() == "a" and current_mode != "SEARCH" and video_id and song_info.get("title") != "No Track Loaded":
                    popup_mode = "ADD_TO_PLAYLIST"
                    popup_idx = 0
                    continue

                if key.name == "KEY_ESCAPE":
                    if current_mode in ("SEARCH", "PLAYLISTS", "SETTINGS"):
                        current_mode = "HOME"
                    continue

                # --- КЕРУВАННЯ HOME DASHBOARD ---
                if current_mode == "HOME":
                    if not home_data:
                        continue

                    if key.name == "KEY_DOWN":
                        home_row_idx = min(len(home_data) - 1, home_row_idx + 1)
                        home_col_idx = 0
                    elif key.name == "KEY_UP":
                        home_row_idx = max(0, home_row_idx - 1)
                        home_col_idx = 0
                    elif key.name == "KEY_RIGHT":
                        items_len = len(home_data[home_row_idx]["items"])
                        home_col_idx = min(items_len - 1, home_col_idx + 1)
                    elif key.name == "KEY_LEFT":
                        home_col_idx = max(0, home_col_idx - 1)
                    elif key.name == "KEY_ENTER":
                        chosen = home_data[home_row_idx]["items"][home_col_idx]
                        target_vid = chosen.get("id")

                        if process:
                            process.kill()

                        if not target_vid and chosen.get("playlistId"):
                            try:
                                pl = yt_client.get_playlist(chosen["playlistId"])
                                tracks = pl.get("tracks", [])
                                if tracks:
                                    target_vid = tracks[0].get("videoId")
                                    chosen["id"] = target_vid
                                    autoplay_tracks = [{"id": t.get("videoId"), "title": t.get("title"), "artist": t.get("artists", [{"name": "Unknown"}])[0]["name"] if t.get("artists") else "Unknown", "source": "youtube"} for t in tracks[1:] if t.get("videoId")]
                            except Exception:
                                pass
                        elif not target_vid and chosen.get("browseId"):
                            try:
                                al = yt_client.get_album(chosen["browseId"])
                                tracks = al.get("tracks", [])
                                if tracks:
                                    target_vid = tracks[0].get("videoId")
                                    chosen["id"] = target_vid
                                    autoplay_tracks = [{"id": t.get("videoId"), "title": t.get("title"), "artist": t.get("artists", [{"name": "Unknown"}])[0]["name"] if t.get("artists") else "Unknown", "source": "youtube"} for t in tracks[1:] if t.get("videoId")]
                            except Exception:
                                pass

                        if target_vid:
                            try:
                                song_info, art_panel, process, auto_q = start_track(chosen)
                                if not autoplay_tracks:
                                    autoplay_tracks = auto_q
                                video_id = target_vid
                                is_paused = False
                                paused_time_accumulated = 0
                                start_time = time.time()
                                total_duration = int(song_info["duration_seconds"])
                                current_mode = "PLAYER"
                                add_to_history(target_vid, song_info.get("title", "Unknown"), song_info["artists"][0]["name"], chosen.get("source", "youtube"), song_info.get("thumbnails"))
                            except Exception:
                                pass

                # --- КЕРУВАННЯ НАЛАШТУВАННЯМИ ---
                elif current_mode == "SETTINGS":
                    if key.name == "KEY_DOWN":
                        settings_idx = min(8, settings_idx + 1)
                    elif key.name == "KEY_UP":
                        settings_idx = max(0, settings_idx - 1)
                    elif key.name == "KEY_RIGHT" and settings_idx == 1:
                        settings["default_volume"] = min(100, settings.get("default_volume", 50) + 5)
                        current_volume = settings["default_volume"]
                        set_system_volume(current_volume)
                        save_settings(settings)
                    elif key.name == "KEY_LEFT" and settings_idx == 1:
                        settings["default_volume"] = max(0, settings.get("default_volume", 50) - 5)
                        current_volume = settings["default_volume"]
                        set_system_volume(current_volume)
                        save_settings(settings)
                    elif key.name == "KEY_RIGHT" and settings_idx == 2:
                        themes = list(THEMES.keys())
                        cur_idx = themes.index(settings.get("theme", "Cyberpunk"))
                        settings["theme"] = themes[(cur_idx + 1) % len(themes)]
                        console.push_theme(THEMES[settings["theme"]])
                        save_settings(settings)
                    elif key.name == "KEY_LEFT" and settings_idx == 2:
                        themes = list(THEMES.keys())
                        cur_idx = themes.index(settings.get("theme", "Cyberpunk"))
                        settings["theme"] = themes[(cur_idx - 1) % len(themes)]
                        console.push_theme(THEMES[settings["theme"]])
                        save_settings(settings)
                    elif key.name == "KEY_ENTER" or str(key) == " ":
                        if settings_idx == 0:
                            settings["cava_enabled"] = not settings.get("cava_enabled", True)
                            cava_enabled = settings["cava_enabled"]
                            save_settings(settings)
                        elif settings_idx == 3:
                            settings["discord_rpc_enabled"] = not settings.get("discord_rpc_enabled", False)
                            save_settings(settings)
                            if not settings["discord_rpc_enabled"]:
                                import discord_rpc
                                discord_rpc.clear_presence()
                        elif settings_idx == 4:
                            settings["notifications_enabled"] = not settings.get("notifications_enabled", True)
                            save_settings(settings)
                        elif settings_idx == 5:
                            import shutil
                            try:
                                shutil.rmtree(CACHE_DIR)
                                os.makedirs(CACHE_DIR, exist_ok=True)
                                toast_message = "Cache Cleared!"
                            except Exception:
                                toast_message = "Failed to clear cache"
                            toast_time = time.time()
                        elif settings_idx == 6:
                            history_path = os.path.expanduser("~/.musicbeast/history.json")
                            if os.path.exists(history_path):
                                os.remove(history_path)
                            history_tracks.clear()
                            toast_message = "History Cleared!"
                            toast_time = time.time()
                        elif settings_idx == 7:
                            popup_mode = "YT_LOGIN"
                            popup_text = ""
                            popup_idx = 0
                        elif settings_idx == 8:
                            popup_mode = "SC_LOGIN"
                            popup_text = ""
                            popup_idx = 0

                # --- КЕРУВАННЯ ПЛЕЙЛІСТАМИ ---
                elif current_mode == "PLAYLISTS":
                    all_pls = list(cached_all_pls)
                    yt_cache = globals().get("yt_playlists_cache")
                    if yt_cache is not None:
                        all_pls.extend(yt_cache)
                    elif globals().get("yt_playlists_loading"):
                        all_pls.append({"id": "loading", "name": "Loading Linked Playlists...", "tracks": [], "is_youtube": True})

                    if key.name == "KEY_RIGHT" and pl_focus == "list" and all_pls:
                        pl_focus = "tracks"
                        pl_track_idx = 0
                    elif key.name == "KEY_LEFT" and pl_focus == "tracks":
                        pl_focus = "list"

                    elif key.name == "KEY_DOWN":
                        if pl_focus == "list":
                            pl_list_idx = min(len(all_pls) - 1, pl_list_idx + 1) if all_pls else 0
                            pl_track_idx = 0
                        else:
                            tracks = all_pls[pl_list_idx].get("tracks", []) if all_pls else []
                            pl_track_idx = min(len(tracks) - 1, pl_track_idx + 1) if tracks else 0

                    elif key.name == "KEY_UP":
                        if pl_focus == "list":
                            pl_list_idx = max(0, pl_list_idx - 1)
                            pl_track_idx = 0
                        else:
                            pl_track_idx = max(0, pl_track_idx - 1)

                    elif key.lower() == "c":
                        popup_mode = "CREATE_PLAYLIST"
                        popup_text = ""

                    elif key.lower() == "x":
                        if pl_focus == "list" and all_pls:
                            deleted_name = all_pls[pl_list_idx]["name"]
                            delete_playlist(all_pls[pl_list_idx]["id"])
                            refresh_local_playlists()
                            pl_list_idx = max(0, pl_list_idx - 1)
                            toast_message = f"Deleted '{deleted_name}'"
                            toast_time = time.time()
                        elif pl_focus == "tracks" and all_pls:
                            pl = all_pls[pl_list_idx]
                            if pl.get("is_youtube") or pl.get("is_spotify") or pl.get("is_soundcloud"):
                                pass  # Cannot delete tracks from remote playlists
                            else:
                                tracks = pl.get("tracks", [])
                            if tracks and 0 <= pl_track_idx < len(tracks):
                                removed_name = tracks[pl_track_idx]["title"]
                                remove_track(all_pls[pl_list_idx]["id"], pl_track_idx)
                                refresh_local_playlists()
                                pl_track_idx = max(0, pl_track_idx - 1)
                                toast_message = f"Removed '{removed_name}'"
                                toast_time = time.time()

                    elif key.name == "KEY_ENTER" and all_pls:
                        if pl_focus == "list":
                            # Грає весь плейліст
                            tracks = all_pls[pl_list_idx].get("tracks", [])
                            if tracks:
                                first = tracks[0]
                                target_vid = first.get("id", first.get("videoId"))
                                if target_vid:
                                    if process: process.kill()
                                    try:
                                        song_info, art_panel, process, _ = start_track(first)
                                        video_id = target_vid
                                        autoplay_tracks = [t for t in tracks[1:] if t.get("id", t.get("videoId"))]
                                        is_paused = False
                                        paused_time_accumulated = 0
                                        start_time = time.time()
                                        total_duration = int(song_info["duration_seconds"])
                                        current_mode = "PLAYER"
                                        add_to_history(target_vid, song_info.get("title", "Unknown"), song_info["artists"][0]["name"], first.get("source", "youtube"), song_info.get("thumbnails"))
                                        toast_message = f"Playing '{all_pls[pl_list_idx]['name']}'"
                                        toast_time = time.time()
                                    except Exception:
                                        pass
                        elif pl_focus == "tracks":
                            # Грає окремий трек
                            tracks = all_pls[pl_list_idx].get("tracks", [])
                            if tracks and 0 <= pl_track_idx < len(tracks):
                                target_vid = tracks[pl_track_idx].get("id", tracks[pl_track_idx].get("videoId"))
                                if target_vid:
                                    if process: process.kill()
                                    try:
                                        song_info, art_panel, process, _ = start_track(tracks[pl_track_idx])
                                        video_id = target_vid
                                        autoplay_tracks = [t for t in tracks[pl_track_idx+1:] if t.get("id", t.get("videoId"))]
                                        is_paused = False
                                        paused_time_accumulated = 0
                                        start_time = time.time()
                                        total_duration = int(song_info["duration_seconds"])
                                        current_mode = "PLAYER"
                                        add_to_history(target_vid, song_info.get("title", "Unknown"), song_info["artists"][0]["name"], tracks[pl_track_idx].get("source", "youtube"), song_info.get("thumbnails"))
                                    except Exception:
                                        pass

                # --- КЕРУВАННЯ ПОШУКОМ ---
                elif current_mode == "SEARCH":
                    if key.name == "KEY_ENTER" and search_query:
                        if not search_results:
                            try:
                                search_results = search_all(search_query)
                                selected_result_idx = 0
                                search_page = 0
                            except Exception:
                                pass
                        else:
                            if process:
                                process.kill()
                            chosen = search_results[selected_result_idx]

                            video_id = chosen.get("id")
                            if video_id:
                                try:
                                    song_info, art_panel, process, auto_q = start_track(chosen)
                                    autoplay_tracks = auto_q
                                    is_paused = False
                                    paused_time_accumulated = 0
                                    start_time = time.time()
                                    total_duration = int(song_info["duration_seconds"])
                                    search_results = []
                                    current_mode = "PLAYER"
                                    # Зберігаємо в історію
                                    artist_for_hist = "Unknown"
                                    if song_info.get("artists"): artist_for_hist = song_info["artists"][0]["name"]
                                    elif song_info.get("author"): artist_for_hist = song_info["author"]
                                    add_to_history(video_id, song_info.get("title", "Unknown"), artist_for_hist, chosen.get("source", "youtube"), song_info.get("thumbnails"))
                                except Exception:
                                    pass

                    elif key.name == "KEY_DOWN" and search_results:
                        selected_result_idx = (selected_result_idx + 1) % len(search_results)
                        search_page = selected_result_idx // ITEMS_PER_PAGE
                    elif key.name == "KEY_UP" and search_results:
                        selected_result_idx = (selected_result_idx - 1) % len(search_results)
                        search_page = selected_result_idx // ITEMS_PER_PAGE
                    elif key.name == "KEY_RIGHT" and search_results:
                        tp = (len(search_results) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
                        search_page = (search_page + 1) % tp
                        selected_result_idx = search_page * ITEMS_PER_PAGE
                    elif key.name == "KEY_LEFT" and search_results:
                        tp = (len(search_results) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
                        search_page = (search_page - 1) % tp
                        selected_result_idx = search_page * ITEMS_PER_PAGE
                    elif key.name == "KEY_BACKSPACE":
                        search_query = search_query[:-1]
                        search_results = []
                    elif not key.is_sequence:
                        search_query += key
                        search_results = []

                # --- ГЛОБАЛЬНЕ КЕРУВАННЯ ПЛЕЄРОМ ---
                if process and current_mode != "SEARCH" and not popup_mode:
                    if key == " ":
                        if not is_paused:
                            process.send_signal(signal.SIGSTOP)
                            pause_start_mark = time.time()
                            is_paused = True
                        else:
                            process.send_signal(signal.SIGCONT)
                            paused_time_accumulated += (time.time() - pause_start_mark)
                            is_paused = False
                    elif key in ("+", "="):
                        current_volume = min(current_volume + 5, 100)
                        set_system_volume(current_volume)
                    elif key in ("-", "_"):
                        current_volume = max(current_volume - 5, 0)
                        set_system_volume(current_volume)

                    elif current_mode == "PLAYER":  # Перемотка тільки в повноекранному режимі
                        if key.name == "KEY_RIGHT":
                            new_target = elapsed + 5
                            if new_target > total_duration:
                                new_target = total_duration - 2
                            if process:
                                process.kill()
                            try:
                                song_info, art_panel, process, _ = start_track({"id": video_id, "title": song_info.get("title"), "artist": song_info["artists"][0]["name"], "source": song_info.get("source", "youtube"), "thumbnails": song_info.get("thumbnails")}, start_seconds=new_target)
                                start_time = time.time() - new_target
                                paused_time_accumulated = 0
                                is_paused = False
                            except Exception:
                                process = None

                        elif key.name == "KEY_LEFT":
                            new_target = max(0, elapsed - 5)
                            if process:
                                process.kill()
                            try:
                                song_info, art_panel, process, _ = start_track({"id": video_id, "title": song_info.get("title"), "artist": song_info["artists"][0]["name"], "source": song_info.get("source", "youtube"), "thumbnails": song_info.get("thumbnails")}, start_seconds=new_target)
                                start_time = time.time() - new_target
                                paused_time_accumulated = 0
                                is_paused = False
                            except Exception:
                                process = None

                    if key.lower() == "n":
                        history_tracks.append({"video_id": video_id, "info": {"id": video_id, "title": song_info.get("title"), "artist": song_info["artists"][0]["name"], "source": song_info.get("source", "youtube"), "thumbnails": song_info.get("thumbnails")}, "art": art_panel})
                        process.kill()
                        # Override repeat so it actually goes to next
                        if is_repeating:
                            is_repeating = False
                            toast_message = "Repeat Disabled"
                            toast_time = time.time()
                    elif key.lower() == "b" and history_tracks:
                        prev = history_tracks.pop()
                        video_id = prev["video_id"]
                        process.kill()
                        try:
                            song_info, art_panel, process, autoplay_tracks = start_track(prev["info"]) # Assuming history info is full
                            start_time = time.time()
                            paused_time_accumulated = 0
                            total_duration = int(song_info["duration_seconds"])
                        except Exception:
                            process = None

    except KeyboardInterrupt:
        pass
    finally:
        if process:
            process.kill()
