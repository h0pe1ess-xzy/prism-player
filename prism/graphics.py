import os
import math
import random
import requests
from PIL import Image
from rich.text import Text
from prism.core.config import CACHE_DIR, safe_cache_id
import time
from io import BytesIO

def download_cover_to_cache(cache_id, thumbnails_list):
    """Завантажує обкладинку за будь-яким ID (videoId, playlistId, browseId)."""
    if not cache_id:
        return None
    img_data = None
    # Спочатку пробуємо thumbnails з API (працює для всіх типів контенту)
    if thumbnails_list and len(thumbnails_list) > 0:
        for thumb in reversed(thumbnails_list):  # Від найбільшого до найменшого
            try:
                url = thumb.get("url") if isinstance(thumb, dict) else str(thumb)
                res = requests.get(url, timeout=3)
                if res.status_code == 200:
                    img_data = res.content
                    break
            except Exception:
                continue

    # YouTube fallback тільки для video-подібних ID (11 символів)
    if not img_data and len(str(cache_id)) == 11:
        try:
            res = requests.get(f"https://img.youtube.com/vi/{cache_id}/hqdefault.jpg", timeout=3)
            if res.status_code == 200:
                img_data = res.content
        except Exception:
            pass

    if img_data:
        try:
            img = Image.open(BytesIO(img_data)).convert('RGB')
            target_path = os.path.join(CACHE_DIR, f"{safe_cache_id(cache_id)}.png")
            img.save(target_path, "PNG")
            return target_path
        except Exception:
            pass
    return None

def generate_ansi_art(video_id, thumbnails_list, width=46):
    if not video_id:
        return Text("\n[ Search for a track to load artwork ]\n", style="dim grey50")
    target_path = os.path.join(CACHE_DIR, f"{safe_cache_id(video_id)}.png")
    if not os.path.exists(target_path):
        target_path = download_cover_to_cache(video_id, thumbnails_list)
    if not target_path or not os.path.exists(target_path):
        return Text("\n[ No Cover Data Available ]\n", style="dim red")

    try:
        img = Image.open(target_path)
        height = 24
        img = img.resize((width, height), Image.Resampling.BILINEAR)
        art_text = Text()
        for y in range(0, img.height, 2):
            for x in range(img.width):
                r1, g1, b1 = img.getpixel((x, y))
                if y + 1 < img.height:
                    r2, g2, b2 = img.getpixel((x, y + 1))
                else:
                    r2, g2, b2 = 0, 0, 0
                art_text.append("▀", style=f"rgb({r1},{g1},{b1}) on rgb({r2},{g2},{b2})")
            art_text.append("\n")
        return art_text
    except Exception:
        return Text("\n[ Cover Render Error ]\n", style="dim red")

def generate_mini_art(item_id, thumbnails_list=None, width=20, height=10):
    """Генерує мініатюрний ASCII-арт для карточок дашборду.
    Приймає будь-який ID (videoId, playlistId, browseId).
    height=10 пікселів → 5 рядків символів (half-block)."""
    global mini_art_cache
    if not item_id:
        placeholder = Text()
        for _ in range(height // 2):
            placeholder.append("░" * width + "\n", style="dim grey30")
        return placeholder

    if item_id in mini_art_cache:
        return mini_art_cache[item_id]

    target_path = os.path.join(CACHE_DIR, f"{safe_cache_id(item_id)}.png")
    if not os.path.exists(target_path):
        # Плейсхолдер "завантажується" — НЕ кешуємо
        placeholder = Text()
        for row in range(height // 2):
            if row == height // 4:
                pad = max(0, (width - 10) // 2)
                placeholder.append(" " * pad + "Loading..." + " " * max(0, width - pad - 10) + "\n", style="dim grey50 on grey11")
            else:
                placeholder.append("░" * width + "\n", style="dim grey30")
        return placeholder

    try:
        img = Image.open(target_path)
        img = img.resize((width, height), Image.Resampling.BILINEAR)
        art_text = Text()
        for y in range(0, img.height, 2):
            for x in range(img.width):
                r1, g1, b1 = img.getpixel((x, y))
                if y + 1 < img.height:
                    r2, g2, b2 = img.getpixel((x, y + 1))
                else:
                    r2, g2, b2 = 0, 0, 0
                art_text.append("▀", style=f"rgb({r1},{g1},{b1}) on rgb({r2},{g2},{b2})")
            art_text.append("\n")
        mini_art_cache[item_id] = art_text
        return art_text
    except Exception:
        placeholder = Text()
        for _ in range(height // 2):
            placeholder.append("░" * width + "\n", style="dim grey30")
        return placeholder

def get_cava_color(y_ratio):
    if y_ratio < 0.3:
        return "secondary.bold"
    elif y_ratio < 0.7:
        return "tertiary.bold"
    else:
        return "primary.bold"

def generate_smooth_cava_horizontal(max_width, height, is_active, side="left"):
    global cava_states
    if max_width < 1 or height < 1:
        return Text("")
    if side not in cava_states or len(cava_states[side]) != height:
        cava_states[side] = [0.0] * height

    levels = cava_states[side]
    t = time.time()

    if is_active:
        for y in range(height):
            if y % 2 != 0:
                continue
            phase = (y * 0.4) if side == "left" else (-y * 0.4 + 10)
            wave = (math.sin(t * 6.0 + phase) + 1.0) / 2.0
            beat = 1.0 if random.random() > 0.85 else 0.0
            center_dist = abs(y - height / 2) / (height / 2)
            length_multiplier = 1.0 - (center_dist * 0.3)
            target = (wave * 0.35 + beat * 0.65) * max_width * length_multiplier

            if target > levels[y]:
                levels[y] += (target - levels[y]) * 0.6
            else:
                levels[y] -= max_width * 0.06
            levels[y] = max(0.0, min(float(max_width), levels[y]))
    else:
        for y in range(height):
            levels[y] -= max_width * 0.06
            levels[y] = max(0.0, levels[y])

    result = Text(justify="right" if side == "right" else "left")
    for y in range(height):
        if y % 2 != 0:
            if y < height - 1:
                result.append("\n")
            continue

        y_ratio = y / height
        color = get_cava_color(y_ratio)
        bar_len = int(levels[y])
        rem = levels[y] - bar_len

        tip = ""
        if rem > 0.66:
            tip = "▓"
        elif rem > 0.33:
            tip = "▒"

        if side == "left":
            char_block = ("█" * bar_len) + tip
        else:
            char_block = tip + ("█" * bar_len)

        if char_block:
            result.append(char_block, style=color)
        if y < height - 1:
            result.append("\n")

    return result

