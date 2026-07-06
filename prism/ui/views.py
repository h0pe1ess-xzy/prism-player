import time

import os
from rich.text import Text
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.console import Group
from rich.align import Align
from rich.progress_bar import ProgressBar
from prism.graphics import generate_smooth_cava_horizontal

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

def draw_settings_view(settings, focus_idx, term_width, term_height, mini_player):
    popup_width = min(50, term_width - 10)
    content = Text()
    content.append("\n  ⚙️ Settings\n", style="primary.bold")
    content.append("  " + "─" * (popup_width - 8) + "\n\n", style="dim grey30")

    is_logged_in = os.path.exists(os.path.expanduser("~/.musicbeast/headers_auth.json"))
    yt_status = "Logged In" if is_logged_in else "Not Logged In"
    sc_status = "Logged In" if settings.get("soundcloud_token") else "Not Logged In"
    discord_rpc = "ON" if settings.get("discord_rpc_enabled") else "OFF"

    notifs = "ON" if settings.get("notifications_enabled", True) else "OFF"

    items = [
        f"Visualizer (Cava): [{'ON' if settings.get('cava_enabled') else 'OFF'}]",
        f"Default Volume:    [{settings.get('default_volume', 50)}]",
        f"Theme:             [{settings.get('theme', 'Cyberpunk')}]",
        f"Discord RPC:       [{discord_rpc}]",
        f"Desktop Notifs:    [{notifs}]",
        f"Clear Art Cache",
        f"Clear Listening History",
        f"Linked Account: YouTube    [{yt_status}]",
        f"Linked Account: SoundCloud [{sc_status}]"
    ]

    for i, item_text in enumerate(items):
        pointer = "▸ " if i == focus_idx else "  "
        if i == focus_idx:
            content.append(f"  {pointer}{item_text}\n", style="primary_inv")
        else:
            content.append(f"  {pointer}{item_text}\n", style="white")

    content.append("\n  " + "─" * (popup_width - 8) + "\n", style="dim grey30")
    content.append("  Made with ❤️ by h0pe1ess\n", style="secondary.bold")
    content.append("\n")
    popup_panel = Panel(
        content,
        width=popup_width,
        border_style="secondary.bold",
        title="♫",
        title_align="center",
        subtitle="[↕] Select │ [↔] Adjust │ [Enter/Space] Toggle │ [Esc] Back",
        subtitle_align="center"
    )

    root_layout = Layout()
    root_layout.split_column(
        Layout(name="main", ratio=1),
        Layout(name="soundbar", size=4),
        Layout(name="footer", size=1)
    )
    root_layout["main"].update(Align.center(popup_panel, vertical="middle"))
    root_layout["soundbar"].update(mini_player)
    root_layout["footer"].update(Align.center(Text("[↕] Select │ [↔] Adjust │ [Enter/Space] Toggle │ [Esc] Back", style="dim grey50")))
    return root_layout

def draw_playlists_view(all_playlists, pl_idx, track_idx, focus, term_width, term_height, mini_player):
    """Вʼю для перегляду та керування кастомними плейлістами."""
    # Ліва панель: список плейлістів
    left_content = Text()
    left_content.append("  📋 My Playlists\n", style="secondary.bold")
    left_content.append("  " + "─" * 22 + "\n\n", style="dim grey30")

    if not all_playlists:
        left_content.append("\n  No playlists yet.\n", style="dim grey50")
        left_content.append("  Press [C] to create!\n", style="primary.dim")
    else:
        for i, pl in enumerate(all_playlists):
            is_active = (i == pl_idx)
            count = len(pl.get("tracks", []))
            pointer = "▸ " if is_active else "  "
            if is_active and focus == "list":
                left_content.append(f"  {pointer}{pl['name']}  ({count})\n", style="bold black on primary")
            elif is_active:
                left_content.append(f"  {pointer}{pl['name']}  ({count})\n", style="primary.bold")
            else:
                left_content.append(f"  {pointer}{pl['name']}  ({count})\n", style="white")

    left_content.append("\n")
    left_content.append("  [C] New  [X] Delete\n", style="dim grey37")

    left_border = "secondary.bold" if focus == "list" else "grey23"
    left_panel = Panel(left_content, border_style=left_border, title="♫ Playlists", title_align="left", style="")

    # Права панель: треки обраного плейлісту
    right_content = Text()
    if all_playlists and 0 <= pl_idx < len(all_playlists):
        pl = all_playlists[pl_idx]
        tracks = pl.get("tracks", [])
        right_content.append(f"  ♫ {pl['name']}\n", style="primary.bold")
        right_content.append(f"  {len(tracks)} tracks\n", style="dim grey50")
        right_content.append("  " + "─" * 30 + "\n\n", style="dim grey30")

        if not tracks:
            right_content.append("\n  Empty playlist.\n", style="dim grey50")
            right_content.append("  Play a song and press [A]\n", style="primary.dim")
            right_content.append("  to add tracks here!\n", style="primary.dim")
        else:
            # Обмежуємо видимі треки до висоти терміналу
            visible_count = max(5, term_height - 14)
            scroll_start = max(0, track_idx - visible_count // 2)
            scroll_end = min(len(tracks), scroll_start + visible_count)

            for i in range(scroll_start, scroll_end):
                track = tracks[i]
                is_active = (i == track_idx) and focus == "tracks"
                pointer = "▶ " if is_active else "  "
                title = track.get('title', 'Unknown')
                artist = track.get('artist', 'Unknown')
                if len(title) > 30:
                    title = title[:28] + ".."
                if is_active:
                    right_content.append(f"  {pointer}{title}\n", style="bold black on primary")
                    right_content.append(f"      {artist}\n", style="bold black on primary")
                else:
                    right_content.append(f"  {pointer}{title}\n", style="white")
                    right_content.append(f"      {artist}\n", style="primary.dim")

            if len(tracks) > visible_count:
                right_content.append(f"\n  ... {len(tracks)} total tracks", style="dim grey50")
    else:
        right_content.append("\n  ← Select a playlist\n", style="dim grey50")

    right_content.append("\n")
    right_content.append("  [X] Remove track\n", style="dim grey37")

    right_border = "primary.bold" if focus == "tracks" else "grey23"
    right_panel = Panel(right_content, border_style=right_border, title="♪ Tracks", title_align="left", style="")

    # Збираємо layout
    root_layout = Layout()
    root_layout.split_column(
        Layout(name="header", size=6),
        Layout(name="body", ratio=1),
        Layout(name="soundbar", size=4),
        Layout(name="footer", size=1)
    )

    header_group = Group(*generate_app_header(term_width))
    root_layout["header"].update(header_group)

    root_layout["body"].split_row(
        Layout(name="left", size=min(32, term_width // 3)),
        Layout(name="right", ratio=1)
    )
    root_layout["body"]["left"].update(left_panel)
    root_layout["body"]["right"].update(right_panel)
    root_layout["soundbar"].update(mini_player)
    root_layout["footer"].update(Align.center(Text(
        "[↕] Navigate │ [←→] Switch │ [Enter] Play │ [C] Create │ [X] Delete │ [Esc] Back",
        style="dim grey50"
    )))
    return root_layout

def draw_lyrics_popup(lyrics_data, scroll_idx, elapsed, term_width, term_height, mini_player):
    popup_width = min(60, term_width - 10)
    visible_height = max(5, term_height - 15)
    
    content = Text(justify="center")
    content.append("\n  🎤 Lyrics\n", style="primary.bold")
    content.append("  " + "─" * (popup_width - 8) + "\n\n", style="dim grey30")

    if not lyrics_data:
        content.append("Loading lyrics...\n", style="dim grey50")
    elif lyrics_data.get("type") == "error":
        content.append(f"{lyrics_data.get('text')}\n", style="dim grey50")
    elif lyrics_data.get("type") == "synced":
        lines = lyrics_data["lines"]
        # Find active line
        active_idx = 0
        for i, (t, _) in enumerate(lines):
            if t <= elapsed + 0.5:  # Slight anticipation
                active_idx = i
            else:
                break
        
        # Center the active line
        start_idx = max(0, active_idx - visible_height // 2)
        end_idx = min(len(lines), start_idx + visible_height)
        
        for i in range(start_idx, end_idx):
            _, text = lines[i]
            if i == active_idx:
                content.append(f"▶ {text}\n", style="bold black on primary")
            else:
                content.append(f"  {text}\n", style="white")
    elif lyrics_data.get("type") == "plain":
        lines = lyrics_data["text"].split('\n')
        max_scroll = max(0, len(lines) - visible_height)
        safe_scroll = min(scroll_idx, max_scroll)
        start_idx = max(0, safe_scroll)
        end_idx = min(len(lines), start_idx + visible_height)
        
        for i in range(start_idx, end_idx):
            content.append(f"{lines[i]}\n", style="white")
    
    content.append("\n")

    popup_panel = Panel(
        content,
        width=popup_width,
        border_style="secondary.bold",
        title="♫",
        title_align="center",
        subtitle="[Esc/L] Close │ [↑/↓] Scroll",
        subtitle_align="center"
    )

    root_layout = Layout()
    root_layout.split_column(
        Layout(name="main", ratio=1),
        Layout(name="soundbar", size=4),
        Layout(name="footer", size=1)
    )
    root_layout["main"].update(Align.center(popup_panel, vertical="middle"))
    root_layout["soundbar"].update(mini_player)
    root_layout["footer"].update(Align.center(Text("[Esc/L] Close │ [↑/↓] Scroll", style="dim grey50")))
    return root_layout

def draw_eq_popup(settings, focus_idx, term_width, term_height, mini_player):
    popup_width = min(40, term_width - 10)
    content = Text()
    content.append("\n  🎛️ Audio Equalizer\n", style="primary.bold")
    content.append("  " + "─" * (popup_width - 8) + "\n\n", style="dim grey30")

    bass = settings.get("eq_bass", 0)
    treble = settings.get("eq_treble", 0)
    fx = settings.get("audio_fx", "Normal")

    items = [
        f"Bass:   [{bass:+d}]",
        f"Treble: [{treble:+d}]",
        f"FX:     [{fx}]"
    ]

    for i, item_text in enumerate(items):
        pointer = "▸ " if i == focus_idx else "  "
        if i == focus_idx:
            content.append(f"  {pointer}{item_text}\n", style="primary_inv")
        else:
            content.append(f"  {pointer}{item_text}\n", style="white")

    content.append("\n  (Applies to next track)\n", style="dim grey50")
    
    popup_panel = Panel(
        content,
        width=popup_width,
        border_style="secondary.bold",
        title="♫",
        title_align="center",
        subtitle="[↕] Select │ [↔] Adjust │ [Esc/E] Close",
        subtitle_align="center"
    )

    root_layout = Layout()
    root_layout.split_column(Layout(name="main", ratio=1), Layout(name="soundbar", size=4), Layout(name="footer", size=1))
    root_layout["main"].update(Align.center(popup_panel, vertical="middle"))
    root_layout["soundbar"].update(mini_player)
    root_layout["footer"].update(Align.center(Text("[↕] Select │ [↔] Adjust │ [Esc/E] Close", style="dim grey50")))
    return root_layout

def draw_popup(title, items, selected_idx, term_width, term_height, mini_player,
               input_mode=False, input_text="", footer_hint="", message=""):
    """Малює модальне вікно поверх інтерфейсу."""
    popup_width = min(50, term_width - 10)

    content = Text()
    content.append(f"\n  {title}\n", style="primary.bold")
    content.append("  " + "─" * (popup_width - 8) + "\n\n", style="dim grey30")

    if message:
        content.append(f"  {message}\n\n", style="primary.bold")

    if input_mode:
        content.append(f"  Name: ", style="bold white")
        content.append(f"{input_text}", style="primary.bold")
        content.append("█\n", style="secondary.bold")
    else:
        for i, item_text in enumerate(items):
            pointer = "▸ " if i == selected_idx else "  "
            if i == selected_idx:
                content.append(f"  {pointer}{item_text}\n", style="bold black on primary")
            else:
                content.append(f"  {pointer}{item_text}\n", style="white")

    content.append("\n")

    popup_panel = Panel(
        content,
        width=popup_width,
        border_style="secondary.bold",
        title="♫",
        title_align="center",
        subtitle=footer_hint,
        subtitle_align="center"
    )

    root_layout = Layout()
    root_layout.split_column(
        Layout(name="main", ratio=1),
        Layout(name="soundbar", size=4),
        Layout(name="footer", size=1)
    )
    root_layout["main"].update(Align.center(popup_panel, vertical="middle"))
    root_layout["soundbar"].update(mini_player)
    root_layout["footer"].update(Align.center(Text(footer_hint, style="dim grey50")))
    return root_layout

def draw_home_dashboard(row_idx, col_idx, term_width, term_height, mini_player, home_loading, dashboard_sections, toast_message="", toast_time=0):
    """Генерує преміум дашборд YT Music з ASCII-арт карточками."""
    CARD_WIDTH = 26
    available_height = term_height - 7  # soundbar(4) + footer(1) + header(2)
    card_height_approx = 12  # висота однієї секції (title + card panel)
    max_visible_sections = max(1, available_height // card_height_approx)

    if home_loading:
        c = """         /\\
        /  \\
       /____\\
      /\\    /\\
     /  \\  /  \\
    /____\\/____\\
    \\    /\\    /
     \\  /  \\  /
      \\/____\\/
       \\    /
        \\  /
         \\/"""
        
        loading_text = Text()
        for line in c.split("\n"):
            loading_text.append(line + "\n", style="primary.bold")
        
        loading_text.append("\n")
        loading_text.append(r" ___  ____  __  ___  __  __     ___  __    __   _  _  ____  ____ " + "\n", style="primary.bold")
        loading_text.append(r"(  _ \(  _ \(  )/ __)(  \/  )   (  _ \(  )  / _\ ( \/ )(  __)(  _ \ " + "\n", style="primary.bold")
        loading_text.append(r" )___/ )   / )((__ \  )    (     )___/ )(__/    \ )  /  ) _)  )   / " + "\n", style="primary.bold")
        loading_text.append(r"(__)  (_)\_)(__)(___/(_/\/\_)   (__)  (____)_/\_/(__/  (____)(_)\_) " + "\n", style="primary.bold")
        
        root_layout = Layout()
        root_layout.split_column(Layout(name="main", ratio=1), Layout(name="soundbar", size=4), Layout(name="footer", size=1))
        root_layout["main"].update(Align.center(loading_text, vertical="middle"))
        root_layout["soundbar"].update(mini_player)
        root_layout["footer"].update(Align.center(Text("Fetching latest recommendations...", style="dim grey50")))
        return root_layout

    sections_list = list(generate_app_header(term_width))

    if not home_data:
        sections_list.append(Text("\n   Failed to load dashboard. Try authenticating.\n", style="dim red"))
    else:
        # Визначаємо видимі рядки
        start_row = max(0, row_idx - max_visible_sections // 2)
        end_row = min(len(home_data), start_row + max_visible_sections)
        if end_row - start_row < max_visible_sections:
            start_row = max(0, end_row - max_visible_sections)

        items_per_row = max(1, (term_width - 6) // CARD_WIDTH)

        for r in range(start_row, end_row):
            section = home_data[r]
            is_active_row = (r == row_idx)

            # Назва секції
            arrow = "▸ " if is_active_row else "  "
            title_style = "primary.bold" if is_active_row else "bold grey62"
            section_title = Text(f"{arrow}{section['title']}", style=title_style)

            # Показник позиції (x/total)
            items = section["items"]
            if is_active_row and len(items) > items_per_row:
                col = min(col_idx, len(items) - 1)
                section_title.append(f"  ({col + 1}/{len(items)})", style="dim grey50")

            sections_list.append(section_title)

            # Горизонтальний скролінг
            if is_active_row:
                col = min(col_idx, len(items) - 1)
                window_start = max(0, col - items_per_row // 2)
            else:
                window_start = 0

            window_end = min(len(items), window_start + items_per_row)
            visible_items = items[window_start:window_end]

            # Рендеримо карточки в Rich Table для горизонтального розташування
            card_table = Table(
                show_header=False, show_edge=False, show_lines=False,
                box=None, padding=(0, 0), expand=False
            )
            for _ in visible_items:
                card_table.add_column(width=CARD_WIDTH, no_wrap=True)

            cards = []
            for i, item in enumerate(visible_items):
                actual_idx = window_start + i
                is_active_item = is_active_row and (actual_idx == col_idx)
                cards.append(render_card(item, is_active_item, card_width=CARD_WIDTH))

            if cards:
                card_table.add_row(*cards)

            # Індикатори скролінгу
            scroll_indicator = Text()
            if window_start > 0:
                scroll_indicator.append(" ◂ ", style="secondary.bold")
            else:
                scroll_indicator.append("   ")
            card_group = Group(card_table)
            if window_end < len(items):
                scroll_indicator.append(" " * (CARD_WIDTH * len(visible_items) - 6))
                scroll_indicator.append(" ▸ ", style="secondary.bold")

            sections_list.append(card_group)
            if window_start > 0 or window_end < len(items):
                sections_list.append(scroll_indicator)
            sections_list.append(Text(""))  # Відступ між секціями



    root_layout = Layout()
    root_layout.split_column(
        Layout(name="main", ratio=1),
        Layout(name="soundbar", size=4),
        Layout(name="footer", size=1)
    )
    # Тост повідомлення
    if toast_message and (time.time() - toast_time) < 2.5:
        toast_text = Text(f"  ✅ {toast_message}  ", style="bold black on primary", justify="center")
        sections_list.append(Align.center(toast_text))

    main_content = Group(*sections_list)
    root_layout["main"].update(main_content)
    root_layout["soundbar"].update(mini_player)
    root_layout["footer"].update(Align.center(Text("[↕ ↔] Navigate │ [Enter] Play │ [P] Playlists │ [/] Search │ [S] Settings │ [Tab] Player │ [M] Mini │ [Q] Exit", style="dim grey50")))
    return root_layout

def draw_search_view(query, results, selected_idx, page, items_per_page, term_width, mini_player):
    content = Text(justify="center")
    content.append(f"\n🔍 Universal Search (Songs & Videos): ", style="primary.bold")
    content.append(f"{query}\n\n", style="white underline" if query else "dim grey50")

    if not results:
        content.append("Type your search and hit Enter...\n", style="dim grey50")
    else:
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = results[start_idx:end_idx]
        total_pages = (len(results) + items_per_page - 1) // items_per_page

        content.append(f"Results Page {page + 1}/{total_pages}\n\n", style="bold dim yellow")
        for idx, item in enumerate(page_items):
            global_idx = start_idx + idx
            pointer = "▶ " if global_idx == selected_idx else "  "
            style = "primary_inv" if global_idx == selected_idx else "white"

            title = item.get("title", "Unknown")
            artists = item.get("artist", "Unknown")
            is_video = f"[{str(item.get('source', 'youtube')).upper()}]"

            line = Text(f"{pointer}{title} - {artists} {is_video}\n", style=style)
            content.append(line)

    root_layout = Layout()
    root_layout.split_column(Layout(name="main", ratio=1), Layout(name="soundbar", size=4), Layout(name="footer", size=1))
    root_layout["main"].update(Align.center(content, vertical="middle"))
    root_layout["soundbar"].update(mini_player)
    root_layout["footer"].update(Align.center(Text("[Enter] Play  │  [↔] Pages  │  [↕] Select  │  [Esc] Back", style="dim grey50"), vertical="bottom"))
    return root_layout

def draw_player_view(song_data, art_panel, elapsed, total_duration, volume, is_paused, next_up_title="None", term_width=80, term_height=24, cava_enabled=False):
    app_width = min(46, term_width - 10)
    if app_width < 28:
        app_width = 28

    cur_time = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
    max_time = f"{total_duration // 60:02d}:{total_duration % 60:02d}"
    status_symbol = "⏸" if is_paused else "▶"

    artist_name = "Unknown"
    if song_data.get("artists"):
        artist_name = song_data["artists"][0]["name"]
    elif song_data.get("author"):
        artist_name = song_data["author"]

    meta_stack = Text(justify="center")
    meta_stack.append(f"{song_data.get('title', 'Unknown')}\n", style="bold white")
    meta_stack.append(f"{artist_name}\n", style="primary.bold")

    pbar = ProgressBar(total=total_duration, completed=elapsed, width=app_width, pulse=False, complete_style="primary", finished_style="primary")

    status_stack = Text(justify="center")
    status_stack.append(f"\n{status_symbol}  {cur_time} / {max_time}   │   🔊 Volume: {volume}%\n", style="grey50")
    status_stack.append(f"⏭ Next Song: {next_up_title}\n", style="primary.dim")

    player_group = Group(
        Align.center(art_panel),
        Text(""),
        Align.center(meta_stack),
        Align.center(pbar, width=term_width if not cava_enabled else term_width // 2),
        Align.center(status_stack)
    )

    player_aligned = Align.center(player_group, vertical="middle")

    root_layout = Layout()

    if cava_enabled:
        root_layout.split_row(
            Layout(name="cava_l", size=14),
            Layout(name="main_app", ratio=1),
            Layout(name="cava_r", size=14)
        )
        main_container = root_layout["main_app"]
    else:
        main_container = root_layout

    main_container.split_column(
        Layout(name="spacer_top", ratio=2),
        Layout(name="body", ratio=10),
        Layout(name="spacer_bottom", ratio=2),
        Layout(name="footer_hints", size=2)
    )
    main_container["spacer_top"].update("")
    main_container["spacer_bottom"].update("")
    main_container["body"].update(player_aligned)

    hints_stack = Text(justify="center")
    hints_stack.append("[Space] Pause │ [↔] Skip 5s │ [N] Next │ [B] Prev │ [-/+] Vol │ [L] Lyrics │ [E] EQ\n", style="dim grey37")
    hints_stack.append("[R] Repeat │ [A] Add PL │ [M] Mini │ [Tab] Home │ [/] Search │ [Q] Exit", style="dim grey37")
    main_container["footer_hints"].update(Align.center(hints_stack, vertical="bottom"))

    if cava_enabled:
        is_active = (not is_paused) and (total_duration > 1)
        cava_w = 12
        cava_h = term_height - 2

        root_layout["cava_l"].update(Align.left(generate_smooth_cava_horizontal(cava_w, cava_h, is_active, "left"), vertical="middle"))
        root_layout["cava_r"].update(Align.right(generate_smooth_cava_horizontal(cava_w, cava_h, is_active, "right"), vertical="middle"))

    return root_layout

