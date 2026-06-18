#!/usr/bin/env python3
"""Terminal file browser for selecting a PDF file."""

import curses
import os
import sys
from dataclasses import dataclass

# Characters that cannot appear in Unix filenames — forward slash (path separator)
# Everything else is valid, so we accept any printable key as filter input.
_FILENAME_BLACKLIST = set('/')

SEARCH_HINT = " type to filter"


@dataclass
class BrowserState:
    cwd: str
    selected: int = 0
    scroll: int = 0
    filter_query: str = ""
    open_after: bool = True


def browse(stdscr, start_dir: str, open_after: bool = True) -> tuple[str, bool] | None:
    _init_curses()
    state = BrowserState(os.path.realpath(start_dir), open_after=open_after)

    while True:
        entries_raw = _read_entries(state)
        if entries_raw is None:
            continue

        h, _ = stdscr.getmaxyx()
        list_height = _list_height(h, state.filter_query)
        items = _visible_items(state.cwd, entries_raw, state.filter_query)
        state.selected = max(0, min(state.selected, len(items) - 1))
        state.scroll = _adjust_scroll(state.selected, state.scroll, list_height)

        _render(stdscr, state, items, list_height)
        action = _handle_key(stdscr.getch(), state, items, list_height)

        if action == "quit":
            return None
        if action:
            return action, state.open_after


def _init_curses() -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)   # folders
    curses.init_pair(2, curses.COLOR_WHITE, -1)  # files
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)  # selected
    curses.init_pair(4, curses.COLOR_YELLOW, -1) # header
    curses.init_pair(5, curses.COLOR_GREEN, -1)  # search box highlight
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)   # active search

def _read_entries(state: BrowserState) -> list[str] | None:
    try:
        return os.listdir(state.cwd)
    except PermissionError:
        state.cwd = os.path.dirname(state.cwd)
        state.selected = 0
        state.scroll = 0
        return None


def _visible_items(
    cwd: str, entries_raw: list[str], filter_query: str
) -> list[tuple[str, str, bool]]:
    all_items = _directory_items(cwd, entries_raw) + _pdf_items(cwd, entries_raw)
    if os.path.dirname(cwd) != cwd:
        all_items.insert(0, ("..", os.path.dirname(cwd), True))
    if not filter_query:
        return all_items
    query = filter_query.lower()
    return [item for item in all_items if query in item[0].lower()]


def _directory_items(cwd: str, entries_raw: list[str]) -> list[tuple[str, str, bool]]:
    dirs = sorted(
        [
            name
            for name in entries_raw
            if os.path.isdir(os.path.join(cwd, name)) and not name.startswith(".")
        ],
        key=str.lower,
    )
    return [(f"[{name}]", os.path.join(cwd, name), True) for name in dirs]


def _pdf_items(cwd: str, entries_raw: list[str]) -> list[tuple[str, str, bool]]:
    pdfs = sorted(
        [
            name
            for name in entries_raw
            if name.lower().endswith(".pdf")
            and os.path.isfile(os.path.join(cwd, name))
        ],
        key=str.lower,
    )
    return [(name, os.path.join(cwd, name), False) for name in pdfs]


def _list_height(screen_height: int, filter_query: str) -> int:
    search_bar_lines = 1 if filter_query else 0
    return screen_height - 6 - search_bar_lines


def _adjust_scroll(selected: int, scroll: int, list_height: int) -> int:
    if selected < scroll:
        return selected
    if selected >= scroll + list_height:
        return selected - list_height + 1
    return scroll


def _render(stdscr, state: BrowserState, items, list_height: int) -> None:
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    list_start = 4 + (1 if state.filter_query else 0)

    _draw_header(stdscr, state.cwd, w)
    _draw_search_bar(stdscr, state.filter_query, w)
    _draw_entries(stdscr, state, items, list_start, list_height, w)
    _draw_footer(stdscr, state, items, h, w)

    stdscr.refresh()


def _draw_header(stdscr, cwd: str, width: int) -> None:
    title = " pdf2audio  •  © 2026 Mathias Conradt  •  MIT License  •  https://github.com/mathiasconradt/pdf2audio"
    stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
    stdscr.addstr(0, 0, title[:width - 1].ljust(width - 1))
    stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
    stdscr.addstr(1, 0, "─" * (width - 1))
    stdscr.addstr(2, 0, f" 📁 {cwd}"[:width - 1])
    stdscr.addstr(3, 0, "─" * (width - 1))


def _draw_search_bar(stdscr, filter_query: str, width: int) -> None:
    if not filter_query:
        return
    stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
    stdscr.addstr(4, 0, f" 🔍 {filter_query}"[:width - 1].ljust(width - 1))
    stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)


def _draw_entries(stdscr, state: BrowserState, items, list_start: int, height: int, width: int) -> None:
    if not items:
        msg = "(no matches)" if state.filter_query else "(no PDF files or subdirectories here)"
        stdscr.addstr(list_start, 2, msg)
        return

    visible_items = items[state.scroll:state.scroll + height]
    for offset, (label, _, is_dir) in enumerate(visible_items):
        row = offset + list_start
        is_selected = state.scroll + offset == state.selected
        _draw_entry(stdscr, row, label, is_dir, is_selected, state.filter_query, width)


def _draw_entry(
    stdscr, row: int, label: str, is_dir: bool, is_selected: bool, filter_query: str, width: int
) -> None:
    attr = _entry_attr(is_selected, is_dir)
    line = f"  {label}"
    if filter_query and not is_selected and _draw_match(stdscr, row, line, label, filter_query, width):
        return

    stdscr.attron(attr)
    visible_line = line[:width - 1].ljust(width - 1) if is_selected else line[:width - 1]
    stdscr.addstr(row, 0, visible_line)
    stdscr.attroff(attr)


def _entry_attr(is_selected: bool, is_dir: bool) -> int:
    if is_selected:
        return curses.color_pair(3)
    if is_dir:
        return curses.color_pair(1)
    return curses.color_pair(2)


def _draw_match(stdscr, row: int, line: str, label: str, query: str, width: int) -> bool:
    pos = label.lower().find(query.lower())
    if pos < 0:
        return False

    before = line[:pos + 2]
    match = line[pos + 2:pos + 2 + len(query)]
    after = line[pos + 2 + len(query):]
    stdscr.addstr(row, 0, before[:width - 1])
    stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
    stdscr.addstr(row, len(before), match[:width - 1 - len(before)])
    stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)
    stdscr.addstr(row, len(before) + len(match), after[:width - 1 - len(before) - len(match)])
    return True


def _draw_footer(stdscr, state: BrowserState, items, height: int, width: int) -> None:
    footer_row = height - 2
    if state.filter_query:
        msg = f" {len(items)} match{'es' if len(items) != 1 else ''}"
        stdscr.attron(curses.color_pair(5))
        stdscr.addstr(footer_row, width - len(msg) - 1, msg)
        stdscr.attroff(curses.color_pair(5))
    stdscr.addstr(footer_row, 0, "─" * (width - 1))
    _draw_hints(stdscr, state, height, width)


def _draw_hints(stdscr, state: BrowserState, height: int, width: int) -> None:
    green_attr = curses.color_pair(1) | curses.A_BOLD
    stdscr.move(height - 1, 0)
    col = 0

    for text, is_key in _hints(state):
        remaining = width - 1 - col
        if remaining <= 0:
            break
        visible_text = text[:remaining]
        stdscr.attron(green_attr) if is_key else stdscr.attroff(curses.color_pair(1))
        stdscr.addstr(visible_text)
        col += len(visible_text)

    stdscr.attroff(green_attr)


def _hints(state: BrowserState) -> list[tuple[str, bool]]:
    open_hint = f" open audio: {'on' if state.open_after else 'off'}  "
    if state.filter_query:
        return [
            (" Esc", True), (" clear filter  ", False),
            (" Backspace", True), (" delete  ", False),
            (" Tab", True), (open_hint, False),
            (" Enter", True), (" select", False),
        ]
    return [
        (" ↑↓", True), (" navigate  ", False),
        (" Enter", True), (" select  ", False),
        (" Tab", True), (open_hint, False),
        (" Esc", True), (f" quit{SEARCH_HINT}", False),
    ]


def _handle_key(key: int, state: BrowserState, items, list_height: int) -> str | None:
    if key == 9:
        state.open_after = not state.open_after
    elif key in (curses.KEY_UP, ord("k")):
        state.selected = max(0, state.selected - 1)
    elif key in (curses.KEY_DOWN, ord("j")):
        state.selected = min(len(items) - 1, state.selected + 1)
    elif key in (curses.KEY_PPAGE,):
        state.selected = max(0, state.selected - list_height)
    elif key in (curses.KEY_NPAGE,):
        state.selected = min(len(items) - 1, state.selected + list_height)
    elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
        return _select_item(state, items)
    elif key == 27:
        return _escape(state)
    elif key == curses.KEY_BACKSPACE or key in (curses.KEY_DC, 127, 8):
        _backspace(state)
    else:
        _append_filter_char(key, state)
    return None


def _select_item(state: BrowserState, items) -> str | None:
    if not items:
        return None
    _, path, is_dir = items[state.selected]
    if not is_dir:
        return path
    state.cwd = os.path.realpath(path)
    _reset_selection(state)
    state.filter_query = ""
    return None


def _escape(state: BrowserState) -> str | None:
    if not state.filter_query:
        return "quit"
    state.filter_query = ""
    _reset_selection(state)
    return None


def _backspace(state: BrowserState) -> None:
    if state.filter_query:
        state.filter_query = state.filter_query[:-1]
        _reset_selection(state)


def _append_filter_char(key: int, state: BrowserState) -> None:
    if 32 <= key < 127 and chr(key) not in _FILENAME_BLACKLIST:
        state.filter_query += chr(key)
        _reset_selection(state)


def _reset_selection(state: BrowserState) -> None:
    state.selected = 0
    state.scroll = 0


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
