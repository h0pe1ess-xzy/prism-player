from rich.console import Group
from rich.text import Text
from rich.panel import Panel
from rich.align import Align
from rich.progress_bar import ProgressBar
from prism.graphics import generate_mini_art

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

def draw_mini_soundbar(song_data, elapsed, total_duration, is_paused, term_width):
    """Створює компактний саундбар для навігаційних меню."""
    if not song_data.get("videoId") and song_data.get("title") == "No Track Loaded":
        return Panel(Text("No active playback", justify="center", style="dim grey50"), border_style="dim grey50")

    cur_time = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
    max_time = f"{total_duration // 60:02d}:{total_duration % 60:02d}"
    status = "⏸" if is_paused else "▶"

    artist_name = "Unknown"
    if song_data.get("artists"):
        artist_name = song_data["artists"][0]["name"]
    elif song_data.get("author"):
        artist_name = song_data["author"]
    title = song_data.get("title", "Unknown")

    pbar_width = max(10, term_width - 40)
    pbar = ProgressBar(total=total_duration, completed=elapsed, width=pbar_width, pulse=False, complete_style="primary", finished_style="primary")

    info_text = Text(f"{status} {title} - {artist_name}  [{cur_time} / {max_time}]", style="primary.bold")

    group = Group(
        Align.center(info_text),
        Align.center(pbar)
    )
    return Panel(group, border_style="secondary")

def generate_app_header(term_width):
    """Генерує градієнтний заголовок програми."""
    header = Text(justify="center")
    header.append(r" ___  ____  __  ___  __  __     ___  __    __   _  _  ____  ____ " + "\n", style="primary.bold")
    header.append(r"(  _ \(  _ \(  )/ __)(  \/  )   (  _ \(  )  / _\ ( \/ )(  __)(  _ \ " + "\n", style="primary.bold")
    header.append(r" )___/ )   / )((__ \  )    (     )___/ )(__/    \ )  /  ) _)  )   / " + "\n", style="primary.bold")
    header.append(r"(__)  (_)\_)(__)(___/(_/\/\_)   (__)  (____)_/\_/(__/  (____)(_)\_) " + "\n", style="primary.bold")

    divider = Text(justify="center")
    gradient_chars = "━" * min(60, term_width - 10)
    for i, ch in enumerate(gradient_chars):
        ratio = i / max(1, len(gradient_chars) - 1)
        if ratio < 0.5:
            divider.append(ch, style="secondary")
        else:
            divider.append(ch, style="primary")
    divider.append("\n")

    return [Align.center(header), Align.center(divider)]

