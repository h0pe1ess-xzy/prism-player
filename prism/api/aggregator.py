import threading
import yt_dlp
import requests

def _get_youtube_music_client():
    from ytmusicapi import YTMusic
    import os
    AUTH_FILE = os.path.expanduser("~/.musicbeast/headers_auth.json")
    is_authenticated = os.path.exists(AUTH_FILE)
    try:
        return YTMusic(AUTH_FILE) if is_authenticated else YTMusic()
    except Exception:
        return YTMusic()

yt_client = _get_youtube_music_client()

def refresh_yt_client():
    global yt_client
    yt_client = _get_youtube_music_client()

def get_youtube_playlists():
    import os
    AUTH_FILE = os.path.expanduser("~/.musicbeast/headers_auth.json")
    if not os.path.exists(AUTH_FILE):
        return []
    
    try:
        raw_pls = yt_client.get_library_playlists(limit=10)
        formatted_pls = []
        for p in raw_pls:
            pid = p.get("playlistId")
            if not pid: continue
            
            # Fetch tracks for each playlist
            try:
                details = yt_client.get_playlist(pid, limit=50)
                tracks = []
                for t in details.get("tracks", []):
                    vid = t.get("videoId")
                    if vid:
                        artist_name = "Unknown"
                        if t.get("artists"): artist_name = t["artists"][0]["name"]
                        elif t.get("author"): artist_name = t["author"]
                        tracks.append({
                            "id": vid,
                            "title": t.get("title", "Unknown"),
                            "artist": artist_name,
                            "source": "youtube",
                            "thumbnails": t.get("thumbnails", [])
                        })
                formatted_pls.append({
                    "id": pid,
                    "name": p.get("title", "Unknown"),
                    "tracks": tracks,
                    "is_youtube": True
                })
            except Exception:
                pass
        return formatted_pls
    except Exception:
        return []

def search_youtube(query, limit=10):
    try:
        raw_res = yt_client.search(query, limit=limit)
        results = []
        for r in raw_res:
            vid = r.get("videoId")
            if vid:
                artist_name = "Unknown"
                if r.get("artists"):
                    artist_name = r["artists"][0]["name"]
                elif r.get("author"):
                    artist_name = r["author"]
                results.append({
                    "id": vid,
                    "title": r.get("title", "Unknown"),
                    "artist": artist_name,
                    "source": "youtube",
                    "thumbnails": r.get("thumbnails", [])
                })
        return results
    except Exception:
        return []

def search_soundcloud(query, limit=10):
    try:
        ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'scsearch{limit}:{query}', download=False)
            entries = info.get('entries', [])
            results = []
            for e in entries:
                url = e.get("url")
                if url:
                    results.append({
                        "id": url,
                        "title": e.get("title", "Unknown"),
                        "artist": e.get("uploader", "Unknown"),
                        "source": "soundcloud",
                        "thumbnails": [{"url": e.get("thumbnails", [{}])[0].get("url", "")}] if e.get("thumbnails") else []
                    })
            return results
    except Exception:
        return []

def search_spotify(query, limit=10):
    # Using Spotify web player anonymous token for metadata
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }
        r = requests.get('https://open.spotify.com/get_access_token?reason=transport&productType=web_player', headers=headers, timeout=5)
        data = r.json()
        token = data.get('accessToken', '')
        if token:
            headers = {'Authorization': f'Bearer {token}'}
            sr = requests.get('https://api.spotify.com/v1/search', 
                params={'q': query, 'type': 'track', 'limit': limit},
                headers=headers, timeout=5)
            tracks = sr.json().get('tracks', {}).get('items', [])
            results = []
            for t in tracks:
                artists = ', '.join(a['name'] for a in t['artists'])
                # Convert spotify album images to YTMusic style thumbnails list
                images = t.get('album', {}).get('images', [])
                results.append({
                    "id": t['id'],
                    "title": t['name'],
                    "artist": artists,
                    "source": "spotify",
                    "thumbnails": images
                })
            return results
    except Exception:
        pass
    return []

def search_local(query="", limit=20):
    import os
    import glob
    from mutagen.easyid3 import EasyID3
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    
    music_dir = os.path.expanduser("~/Music")
    if not os.path.exists(music_dir):
        return []
        
    results = []
    extensions = ["*.mp3", "*.flac", "*.m4a", "*.wav", "*.ogg"]
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(music_dir, "**", ext), recursive=True))
        
    for f in files:
        if len(results) >= limit:
            break
            
        filename = os.path.basename(f)
        title = filename
        artist = "Unknown Artist"
        
        try:
            if f.endswith(".mp3"):
                tags = EasyID3(f)
                title = tags.get("title", [title])[0]
                artist = tags.get("artist", [artist])[0]
            elif f.endswith(".flac"):
                tags = FLAC(f)
                title = tags.get("title", [title])[0]
                artist = tags.get("artist", [artist])[0]
            elif f.endswith(".m4a"):
                tags = MP4(f)
                title = tags.get("\xa9nam", [title])[0]
                artist = tags.get("\xa9ART", [artist])[0]
        except Exception:
            pass
            
        search_str = f"{title} {artist} {filename}".lower()
        if not query or query.lower() in search_str:
            results.append({
                "id": f,
                "title": title,
                "artist": artist,
                "source": "local",
                "thumbnails": []
            })
            
    return results

def search_all(query):
    results = []
    yt_res = []
    sc_res = []
    sp_res = []
    loc_res = []
    
    def fetch_yt(): nonlocal yt_res; yt_res = search_youtube(query, 12)
    def fetch_sc(): nonlocal sc_res; sc_res = search_soundcloud(query, 6)
    def fetch_sp(): nonlocal sp_res; sp_res = search_spotify(query, 12)
    def fetch_loc(): nonlocal loc_res; loc_res = search_local(query, 12)
    
    threads = [
        threading.Thread(target=fetch_yt),
        threading.Thread(target=fetch_sc),
        threading.Thread(target=fetch_sp),
        threading.Thread(target=fetch_loc)
    ]
    for t in threads: t.start()
    for t in threads: t.join()
    
    # Interleave results: LOC, SP, YT, SC...
    max_len = max(len(yt_res), len(sc_res), len(sp_res), len(loc_res))
    for i in range(max_len):
        if i < len(loc_res): results.append(loc_res[i])
        if i < len(sp_res): results.append(sp_res[i])
        if i < len(yt_res): results.append(yt_res[i])
        if i < len(sc_res): results.append(sc_res[i])
        
    return results

def get_dashboard_sections():
    sections = []
    
    # Local Music
    try:
        loc_res = search_local(limit=10)
        if loc_res:
            sections.append({"title": "📁 Local Music", "items": loc_res})
    except Exception:
        pass
        
    # Spotify Top Hits
    try:
        sp_res = search_spotify("top hits", 15)
        if sp_res:
            sections.append({"title": "🟢 Spotify Top Hits", "items": sp_res})
    except Exception:
        pass

    # YouTube Music Recommendations
    try:
        raw_home = yt_client.get_home(limit=3)
        for row in raw_home:
            title = row.get("title", "YouTube Recommends")
            contents = row.get("contents", [])
            valid_items = []
            for item in contents:
                vid = item.get("videoId")
                if vid:
                    arts = item.get("artists") or item.get("subtitle") or ""
                    if isinstance(arts, list) and len(arts) > 0: art_name = arts[0].get("name", "")
                    elif isinstance(arts, str): art_name = arts
                    else: art_name = "Various Artists"
                    valid_items.append({
                        "id": vid,
                        "title": item.get("title", "Unknown"),
                        "artist": art_name,
                        "source": "youtube",
                        "thumbnails": item.get("thumbnails", [])
                    })
            if valid_items:
                sections.append({"title": f"📺 {title}", "items": valid_items})
    except Exception:
        pass

    # SoundCloud Trending
    try:
        sc_res = search_soundcloud("trending music", 15)
        if sc_res:
            sections.append({"title": "☁️ SoundCloud Trending", "items": sc_res})
    except Exception:
        pass

    return sections

def get_stream_info(track_id, source, title="", artist=""):
    """
    Returns (stream_url, duration_seconds) for FFplay.
    Resolves Spotify to YouTube audio.
    """
    if not track_id:
        return "", 0
        
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'check_formats': False,
        'extractor_args': {'youtube': ['player_client=android', 'player_skip=webpage']}
    }

    if source == "local":
        import os
        from mutagen import File
        if not os.path.exists(track_id):
            return "", 0
        try:
            audio = File(track_id)
            duration = int(audio.info.length) if audio and audio.info else 240
            return track_id, duration
        except Exception:
            return track_id, 240

    if source == "soundcloud":
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(track_id, download=False)
            return info['url'], info.get('duration', 240)
            
    elif source == "spotify":
        # Search YT Music for equivalent audio
        yt_res = search_youtube(f"{title} {artist}", limit=1)
        if yt_res:
            actual_vid = yt_res[0]["id"]
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://youtube.com/watch?v={actual_vid}", download=False)
                return info['url'], info.get('duration', 240)
    
    # Default: YouTube
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://youtube.com/watch?v={track_id}", download=False)
        return info['url'], info.get('duration', 240)

def get_spotify_playlists():
    import os, json, requests
    auth_path = os.path.expanduser("~/.musicbeast/spotify_auth.json")
    if not os.path.exists(auth_path):
        return []
    try:
        with open(auth_path, "r") as f:
            sp_dc = json.load(f).get("sp_dc")
        if not sp_dc: return []
        
        # Get Token
        r = requests.get('https://open.spotify.com/get_access_token?reason=transport&productType=web_player', cookies={'sp_dc': sp_dc}, timeout=5)
        token = r.json().get('accessToken')
        if not token: return []
        
        headers = {'Authorization': f'Bearer {token}'}
        pls_req = requests.get('https://api.spotify.com/v1/me/playlists', headers=headers, timeout=5)
        raw_pls = pls_req.json().get('items', [])
        
        formatted_pls = []
        for p in raw_pls[:10]:  # Limit to 10
            pid = p.get('id')
            pname = p.get('name', 'Unknown')
            # Get tracks
            try:
                tr_req = requests.get(p.get('tracks', {}).get('href', f'https://api.spotify.com/v1/playlists/{pid}/tracks'), headers=headers, timeout=5)
                raw_tracks = tr_req.json().get('items', [])
                tracks = []
                for item in raw_tracks:
                    t = item.get('track', {})
                    if not t or not t.get('id'): continue
                    artists = ', '.join(a['name'] for a in t.get('artists', []))
                    images = t.get('album', {}).get('images', [])
                    tracks.append({
                        "id": t['id'],
                        "title": t.get('name', 'Unknown'),
                        "artist": artists,
                        "source": "spotify",
                        "thumbnails": images
                    })
                formatted_pls.append({
                    "id": pid,
                    "name": pname + " [SP]",
                    "tracks": tracks,
                    "is_spotify": True
                })
            except Exception:
                pass
        return formatted_pls
    except Exception:
        return []

def get_soundcloud_playlists():
    import os, json, requests
    auth_path = os.path.expanduser("~/.musicbeast/settings.json")
    if not os.path.exists(auth_path):
        return []
    try:
        with open(auth_path, "r") as f:
            token = json.load(f).get("soundcloud_token")
        if not token: return []
        
        headers = {'Authorization': f'OAuth {token}'}
        
        # We also need a client_id for some SC endpoints, but OAuth alone often works for /me
        pls_req = requests.get('https://api-v2.soundcloud.com/me/library/playlists', headers=headers, timeout=5)
        raw_pls = pls_req.json().get('collection', [])
        
        formatted_pls = []
        for p_wrapper in raw_pls[:10]:
            p = p_wrapper.get('playlist', {})
            if not p: continue
            pid = p.get('id')
            pname = p.get('title', 'Unknown')
            tracks = []
            for t in p.get('tracks', []):
                # Sometimes tracks only have IDs, but usually they are populated
                if t.get('title') and t.get('permalink_url'):
                    tracks.append({
                        "id": t.get('permalink_url'),
                        "title": t.get('title', 'Unknown'),
                        "artist": t.get('user', {}).get('username', 'Unknown'),
                        "source": "soundcloud",
                        "thumbnails": [{"url": t.get('artwork_url', '').replace('-large', '-t500x500')}] if t.get('artwork_url') else []
                    })
            if tracks:
                formatted_pls.append({
                    "id": str(pid),
                    "name": pname + " [SC]",
                    "tracks": tracks,
                    "is_soundcloud": True
                })
        return formatted_pls
    except Exception:
        return []

def get_lyrics(title, artist):
    import urllib.parse
    import re
    import requests
    try:
        def fetch(t, a=None):
            if a:
                url = f"https://lrclib.net/api/search?track_name={urllib.parse.quote(t)}&artist_name={urllib.parse.quote(a)}"
            else:
                url = f"https://lrclib.net/api/search?track_name={urllib.parse.quote(t)}"
            headers = {"User-Agent": "PrismPlayer/1.0 (https://github.com/h0pe1ess-xzy/prism-player)"}
            r = requests.get(url, headers=headers, timeout=5)
            r.raise_for_status()
            return r.json()

        # 1. Exact match
        data = fetch(title, artist)
        
        # 1.5 Extract from "Artist - Title" format (common on YouTube)
        extracted_artist = artist
        extracted_title = title
        if " - " in title:
            parts = title.split(" - ", 1)
            extracted_artist = parts[0].strip()
            extracted_title = parts[1].strip()
            if not data:
                data = fetch(extracted_title, extracted_artist)

        # 2. Cleaned title (remove anything in parenthesis/brackets)
        cleaned_title = re.sub(r'[\(\[\{].*?[\)\]\}]', '', extracted_title).strip()
        cleaned_artist = re.sub(r'[\(\[\{].*?[\)\]\}]', '', extracted_artist).strip()
        
        if not data and cleaned_title and cleaned_title.lower() != extracted_title.lower():
            data = fetch(cleaned_title, cleaned_artist)
            
        # 3. Try without artist at all (LRCLIB can fuzzy match just by track_name)
        if not data and cleaned_title:
            data = fetch(cleaned_title, None)
            
        # 4. As a final fallback, try just the first few words of the title
        if not data and cleaned_title:
            short_title = " ".join(cleaned_title.split(" ")[:3])
            data = fetch(short_title, None)

        if not data:
            return {"type": "error", "text": "Lyrics not found for this track."}
        
        # Take the best match
        best = data[0]
        if best.get("syncedLyrics"):
            lines = []
            for line in best["syncedLyrics"].split('\n'):
                match = re.match(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)', line)
                if match:
                    mins = int(match.group(1))
                    secs = float(match.group(2))
                    text = match.group(3).strip()
                    lines.append((mins * 60 + secs, text))
            if lines:
                return {"type": "synced", "lines": lines}
        
        if best.get("plainLyrics"):
            return {"type": "plain", "text": best["plainLyrics"]}
            
        return {"type": "error", "text": "No lyrics content available."}
    except Exception as e:
        return {"type": "error", "text": "Error fetching lyrics (Network issue)."}
