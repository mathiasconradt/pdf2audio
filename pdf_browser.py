#!/usr/bin/env python3
"""Terminal file browser for selecting a PDF file."""

import curses
import os
import sys


def browse(stdscr, start_dir: str) -> str | None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)   # folders
    curses.init_pair(2, curses.COLOR_WHITE, -1)  # files
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)  # selected
    curses.init_pair(4, curses.COLOR_YELLOW, -1) # header

    cwd = os.path.realpath(start_dir)
    selected = 0
    scroll = 0

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        list_height = h - 6  # header (4) + footer (2)

        # Build entries
        try:
            entries_raw = os.listdir(cwd)
        except PermissionError:
            cwd = os.path.dirname(cwd)
            continue

        dirs = sorted([e for e in entries_raw if os.path.isdir(os.path.join(cwd, e))
                       and not e.startswith('.')], key=str.lower)
        pdfs = sorted([e for e in entries_raw if e.lower().endswith('.pdf')
                       and os.path.isfile(os.path.join(cwd, e))], key=str.lower)

        items = []  # (label, path, is_dir)
        is_root = os.path.dirname(cwd) == cwd
        if not is_root:
            items.append(("..", os.path.dirname(cwd), True))
        for d in dirs:
            items.append((f"[{d}]", os.path.join(cwd, d), True))
        for f in pdfs:
            items.append((f, os.path.join(cwd, f), False))

        selected = max(0, min(selected, len(items) - 1))

        # Auto-scroll
        if selected < scroll:
            scroll = selected
        elif selected >= scroll + list_height:
            scroll = selected - list_height + 1

        # Header
        title = " pdf2audio  •  © 2026 Mathias Conradt  •  MIT License  •  https://github.com/mathiasconradt/pdf2audio"
        stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(0, 0, title[:w-1].ljust(w-1))
        stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(1, 0, "─" * (w - 1))
        path_line = f" 📁 {cwd}"
        stdscr.addstr(2, 0, path_line[:w-1])
        stdscr.addstr(3, 0, "─" * (w - 1))

        # Entries
        if not items:
            stdscr.addstr(4, 2, "(no PDF files or subdirectories here)")
        else:
            for i, (label, _, is_dir) in enumerate(items[scroll:scroll + list_height]):
                row = i + 4
                idx = scroll + i
                is_sel = idx == selected

                if is_sel:
                    attr = curses.color_pair(3)
                elif is_dir:
                    attr = curses.color_pair(1)
                else:
                    attr = curses.color_pair(2)

                line = f"  {label}"
                stdscr.attron(attr)
                stdscr.addstr(row, 0, line[:w-1].ljust(w-1) if is_sel else line[:w-1])
                stdscr.attroff(attr)

        # Footer
        stdscr.addstr(h - 2, 0, "─" * (w - 1))
        footer = " ↑↓ navigate  Enter select  q quit"
        stdscr.addstr(h - 1, 0, footer[:w-1])

        stdscr.refresh()

        key = stdscr.getch()

        if key in (curses.KEY_UP, ord('k')):
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
            else:
                return path
        elif key in (ord('q'), ord('Q'), 27):  # q or ESC
            return None


def main():
    start_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    out_file = sys.argv[2] if len(sys.argv) > 2 else None

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
            result = browse(scr, start_dir)
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
        if out_file:
            with open(out_file, "w") as f:
                f.write(result)
        else:
            old_stdout.write(result + "\n")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
