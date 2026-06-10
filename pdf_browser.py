#!/usr/bin/env python3
"""Terminal file browser for selecting a PDF file."""

import curses
import os
import sys

# Characters that cannot appear in Unix filenames — forward slash (path separator)
# Everything else is valid, so we accept any printable key as filter input.
_FILENAME_BLACKLIST = set('/')

SEARCH_HINT = " type to filter"


def browse(stdscr, start_dir: str, open_after: bool = True) -> tuple[str, bool] | None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)   # folders
    curses.init_pair(2, curses.COLOR_WHITE, -1)  # files
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)  # selected
    curses.init_pair(4, curses.COLOR_YELLOW, -1) # header
    curses.init_pair(5, curses.COLOR_GREEN, -1)  # search box highlight
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)   # active search

    cwd = os.path.realpath(start_dir)
    selected = 0
    scroll = 0
    filter_query = ""
    all_items: list[tuple[str, str, bool]] = []

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        # header (4) + search bar (1 when active) + footer (2)
        search_bar_lines = 1 if filter_query else 0
        list_height = h - 6 - search_bar_lines

        # Build entries
        try:
            entries_raw = os.listdir(cwd)
        except PermissionError:
            cwd = os.path.dirname(cwd)
            all_items = []
            continue

        dirs = sorted([e for e in entries_raw if os.path.isdir(os.path.join(cwd, e))
                       and not e.startswith('.')], key=str.lower)
        pdfs = sorted([e for e in entries_raw if e.lower().endswith('.pdf')
                       and os.path.isfile(os.path.join(cwd, e))], key=str.lower)

        all_items = []  # (label, path, is_dir)
        is_root = os.path.dirname(cwd) == cwd
        if not is_root:
            all_items.append(("..", os.path.dirname(cwd), True))
        for d in dirs:
            all_items.append((f"[{d}]", os.path.join(cwd, d), True))
        for f in pdfs:
            all_items.append((f, os.path.join(cwd, f), False))

        # Apply filter (case-insensitive *query* substring match)
        if filter_query:
            items = [
                (label, path, is_dir) for label, path, is_dir in all_items
                if filter_query.lower() in label.lower()
            ]
        else:
            items = list(all_items)

        selected = max(0, min(selected, len(items) - 1))

        # Auto-scroll
        if selected < scroll:
            scroll = selected
        elif selected >= scroll + list_height:
            scroll = selected - list_height + 1

        # Header
        header_offset = 0
        title = " pdf2audio  •  © 2026 Mathias Conradt  •  MIT License  •  https://github.com/mathiasconradt/pdf2audio"
        stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(0 + header_offset, 0, title[:w-1].ljust(w-1))
        stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(1 + header_offset, 0, "─" * (w - 1))
        path_line = f" 📁 {cwd}"
        stdscr.addstr(2 + header_offset, 0, path_line[:w-1])
        stdscr.addstr(3 + header_offset, 0, "─" * (w - 1))

        # Search bar (when filter is active)
        list_start = 4 + search_bar_lines
        if filter_query:
            search_text = f" 🔍 {filter_query}" 
            stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
            stdscr.addstr(4, 0, search_text[:w-1].ljust(w - 1))
            stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)

        # Entries
        if not items:
            msg = "(no matches)" if filter_query else "(no PDF files or subdirectories here)"
            stdscr.addstr(list_start, 2, msg)
        else:
            matched = len(items) if filter_query else None
            for i, (label, _, is_dir) in enumerate(items[scroll:scroll + list_height]):
                row = i + list_start
                idx = scroll + i
                is_sel = idx == selected

                if is_sel:
                    attr = curses.color_pair(3)
                elif is_dir:
                    attr = curses.color_pair(1)
                else:
                    attr = curses.color_pair(2)

                line = f"  {label}"
                # Highlight matching portion when filtering
                if filter_query and not is_sel:
                    lower_label = label.lower()
                    lower_q = filter_query.lower()
                    pos = lower_label.find(lower_q)
                    if pos >= 0:
                        before = line[:pos + 2]  # +2 for "  " prefix
                        match = line[pos + 2:pos + 2 + len(filter_query)]
                        after = line[pos + 2 + len(filter_query):]
                        stdscr.addstr(row, 0, (before if is_sel else before)[:w-1])
                        stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
                        stdscr.addstr(row, len(before), match[:w - 1 - len(before)])
                        stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)
                        stdscr.addstr(row, len(before) + len(match), after)
                    else:
                        stdscr.attron(attr)
                        stdscr.addstr(row, 0, line[:w-1].ljust(w-1) if is_sel else line[:w-1])
                        stdscr.attroff(attr)
                else:
                    stdscr.attron(attr)
                    stdscr.addstr(row, 0, line[:w-1].ljust(w-1) if is_sel else line[:w-1])
                    stdscr.attroff(attr)

        # Footer — show result count when filtering
        footer_row = h - 2
        if filter_query:
            msg = f" {len(items)} match{"es" if len(items) != 1 else ""}"
            stdscr.attron(curses.color_pair(5))
            stdscr.addstr(footer_row, w - len(msg) - 1, msg)
            stdscr.attroff(curses.color_pair(5))
        stdscr.addstr(h - 2, 0, "─" * (w - 1))
        
        # Footer with green key hints (matching folder color)
        green_attr = curses.color_pair(1) | curses.A_BOLD
        stdscr.move(h - 1, 0)

        open_hint = f" open audio: {'on' if open_after else 'off'}  "
        if filter_query:
            hints = [(" Esc", True), (" clear filter  ", False),
                     (" Backspace", True), (" delete  ", False),
                     (" Tab", True), (open_hint, False),
                     (" Enter", True), (" select", False)]
        else:
            hints = [(" ↑↓", True), (" navigate  ", False),
                     (" Enter", True), (" select  ", False),
                     (" Tab", True), (open_hint, False),
                     (" Esc", True), (f" quit{SEARCH_HINT}", False)]

        col = 0
        for text, is_key in hints:
            remaining = w - 1 - col
            if remaining <= 0:
                break
            visible_text = text[:remaining]
            if is_key:
                stdscr.attron(green_attr)
            else:
                stdscr.attroff(curses.color_pair(1))
            stdscr.addstr(visible_text)
            col += len(visible_text)

        stdscr.attroff(green_attr)

        stdscr.refresh()

        key = stdscr.getch()

        if key == 9:  # Tab
            open_after = not open_after
        elif key in (curses.KEY_UP, ord('k')):
            selected = max(0, selected - 1)
        elif key in (curses.KEY_DOWN, ord('j')):
            selected = min(len(items) - 1, selected + 1)
        elif key in (curses.KEY_PPAGE,):  # page up
            selected = max(0, selected - list_height)
        elif key in (curses.KEY_NPAGE,):  # page down
            selected = min(len(items) - 1, selected + list_height)
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            if not items:
                continue
            label, path, is_dir = items[selected]
            if is_dir:
                cwd = os.path.realpath(path)
                selected = 0
                scroll = 0
                filter_query = ""  # Clear filter when navigating into a folder
            else:
                return path, open_after
        elif key == 27:  # ESCAPE — clear filter or quit app
            if filter_query:
                filter_query = ""
                selected = 0
                scroll = 0
            else:
                return None
        elif key == curses.KEY_BACKSPACE or key in (curses.KEY_DC, 127, 8):
            # Backspace — remove last char from filter
            if filter_query:
                filter_query = filter_query[:-1]
                selected = 0
                scroll = 0
        else:
            # Any other printable character -- add to filter
            # Accept all chars valid in Unix filenames (everything except /)
            if 32 <= key < 127 and chr(key) not in _FILENAME_BLACKLIST:
                filter_query += chr(key)
                selected = 0
                scroll = 0


def main():
    start_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    out_file = sys.argv[2] if len(sys.argv) > 2 else None
    open_after = sys.argv[3] != "0" if len(sys.argv) > 3 else True

    # Open /dev/tty directly so curses works inside $() subshell
    import io
    tty_fd = open("/dev/tty", "r+b", buffering=0)
    tty_text = io.TextIOWrapper(tty_fd)
    old_stdin, old_stdout = sys.stdin, sys.stdout
    sys.stdin = tty_text
    sys.stdout = tty_text

    try:
        scr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        scr.keypad(True)
        try:
            result = browse(scr, start_dir, open_after)
        finally:
            scr.keypad(False)
            curses.echo()
            curses.nocbreak()
            curses.endwin()
    finally:
        sys.stdin, sys.stdout = old_stdin, old_stdout
        tty_text.detach()
        tty_fd.close()

    if result:
        selected_path, selected_open_after = result
        if out_file:
            with open(out_file, "w") as f:
                f.write(f"{1 if selected_open_after else 0}\n{selected_path}")
        else:
            old_stdout.write(f"{selected_path}\n")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
