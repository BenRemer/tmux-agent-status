#!/usr/bin/env python3
"""Render real, isolated tmux output as annotated README images.

Only the terminal frame and explanatory captions are drawn by this script.
The terminal contents, status styles, icons, and transitions come from tmux.
No personal configuration or AI service is used.
"""
import argparse
from pathlib import Path
import sys
import time

from PIL import Image, ImageDraw, ImageFont
import pyte

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from integration import Server  # noqa: E402

BG = "#101722"
PANEL = "#171f2d"
FG = "#d7e0ed"
MUTED = "#a0aec2"
TEAL = "#8bd5ca"
AMBER = "#eed49f"
COLORS = {
    "black": "#000000", "red": "#cd0000", "green": "#00cd00",
    "brown": "#cdcd00", "blue": "#0000ee", "magenta": "#cd00cd",
    "cyan": "#00cdcd", "white": "#e5e5e5",
}


def color(value, default):
    if value == "default":
        return default
    return COLORS.get(value, "#" + value)


class Renderer:
    def __init__(self, mono, emoji):
        self.font = ImageFont.truetype(str(mono), 23)
        self.emoji = ImageFont.truetype(str(emoji), 22)
        self.caption = ImageFont.truetype(str(mono), 19)
        self.cw = round(self.font.getlength("M"))
        self.ch = 31

    def terminal(self, server, client, title):
        server.tm("refresh-client", "-R", "-t", client)
        time.sleep(.15)
        screen = DemoScreen(server.columns, server.rows)
        pyte.Stream(screen).feed(bytes(server.clients[0][3]).decode("utf-8", "replace"))
        width, height = server.columns * self.cw, server.rows * self.ch
        image = Image.new("RGB", (width + 48, height + 92), BG)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, image.width - 1, image.height - 1),
                               radius=16, fill=PANEL, outline="#354155", width=1)
        draw.ellipse((24, 25, 33, 34), fill=TEAL)
        draw.text((45, 18), title, fill=MUTED, font=self.caption)
        ox, oy = 24, 64
        draw.rectangle((ox, oy, ox + width, oy + height), fill=BG)
        for row in range(server.rows):
            for col in range(server.columns):
                cell = screen.buffer[row][col]
                fg, bg = color(cell.fg, FG), color(cell.bg, BG)
                if cell.reverse:
                    fg, bg = bg, fg
                x, y = ox + col * self.cw, oy + row * self.ch
                draw.rectangle((x, y, x + self.cw - 1, y + self.ch - 1), fill=bg)
        # Draw glyphs after backgrounds so a wide glyph's second cell cannot erase it.
        for row in range(server.rows):
            for col in range(server.columns):
                cell = screen.buffer[row][col]
                if not cell.data or cell.data == " ":
                    continue
                fg = color(cell.bg, BG) if cell.reverse else color(cell.fg, FG)
                font = self.emoji if "🔔" in cell.data else self.font
                x, y = ox + col * self.cw, oy + row * self.ch
                draw.text((x, y + 2), cell.data, font=font, fill=fg)
        return image

    def compose(self, frames, notes, output):
        width = max(frame.width for _, frame in frames) + 64
        height = 36 + sum(frame.height + 56 for _, frame in frames) + 76
        image = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(image)
        y = 24
        for label, frame in frames:
            draw.text((32, y), label, font=self.caption, fill=FG)
            y += 34
            image.paste(frame, (32, y))
            y += frame.height + 22
        for index, (label, detail, shade) in enumerate(notes):
            x = 32 + index * (width - 64) // len(notes)
            draw.ellipse((x, y + 5, x + 9, y + 14), fill=shade)
            draw.text((x + 20, y - 1), label, font=self.caption, fill=shade)
            draw.text((x, y + 29), detail, font=self.caption, fill=MUTED)
        image.save(output, optimize=True)
        print(output)


class DemoScreen(pyte.Screen):
    def report_device_status(self, *args, **kwargs):
        # tmux probes its client. This offline renderer has no terminal to answer.
        pass


def set_theme(server):
    for key, value in {
        "status-style": "bg=#1e2030,fg=#cad3f5",
        "window-status-style": "bg=#1e2030,fg=#a5adcb",
        "window-status-current-style": "bg=#8bd5ca,fg=#181926,bold",
        "window-status-bell-style": "default",
        "window-status-separator": " ",
        "window-status-format": " #I #W ",
        "window-status-current-format": " #I #W ",
        "status-left": " #S  ",
        "status-left-length": "20",
        "status-right": "",
        "status-right-length": "30",
        "status-justify": "left",
        "visual-bell": "off",
        "terminal-features": "xterm*:RGB",
        "automatic-rename": "off",
    }.items():
        server.tm("set-option", "-g", key, value)


def message(server, pane, heading, lines):
    body = "\x1b[2J\x1b[H\r\n  \x1b[1;36m" + heading + "\x1b[0m\r\n\r\n"
    body += "\r\n".join("  " + line for line in lines)
    server.emit(pane, body + "\r\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", required=True, type=Path)
    parser.add_argument("--emoji-font", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/images")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    renderer = Renderer(args.font, args.emoji_font)
    s = Server(columns=92, rows=9)
    try:
        set_theme(s)
        s.tm("rename-session", "-t", "A", "work")
        s.tm("rename-session", "-t", "B", "research")
        s.tm("rename-window", "-t", "work:0", "shell")
        codex = s.agent("work:1")
        claude = s.agent("work:2", name="claude")
        review = s.agent("work:3")
        remote = s.agent("research:1")
        for target, name in [("work:1", "codex"), ("work:2", "claude"),
                             ("work:3", "review"), ("research:0", "notes"),
                             ("research:1", "agent")]:
            s.tm("rename-window", "-t", target, name)
        client = s.attach("work:0")
        s.load("compact")
        message(s, "work:0", "Keep working. Your agents stay in view.", [
            "The shell is selected. Codex and Claude are working in other tabs.",
            "The review tab has a notification waiting for you.",
            "",
            "No agent logs or transcripts are read to build this status bar.",
        ])
        s.busy(codex)
        s.emit(claude, "\x1b]2;✳ Claude Code\x07")
        s.tm("set-option", "-p", "-t", claude, "@agent-status-busy-command", "claude")
        s.emit(review, "\a")
        s.busy(remote)
        s.emit(remote, "\a")
        overview = renderer.terminal(s, client, "work session")
        renderer.compose([("A compact view of running work and notifications", overview)], [
            ("Selected", "Your current tab", TEAL),
            ("Running", "A soft tab accent", "#91b9bf"),
            ("Notification", "Stays until visited", AMBER),
            ("Other sessions", "Shown at the right", AMBER),
        ], args.output / "overview.png")

        # A genuinely different client session makes the cross-session case visible.
        s.busy(remote, False)
        message(s, "work:0", "An agent finished in the research session.", [
            "You are still in work. The bell at the right points to another session.",
            "Switch sessions and visit the notified window to acknowledge it.",
        ])
        pending = renderer.terminal(s, client, "work session | research has a notification")
        s.tm("switch-client", "-c", client, "-t", "research:1")
        s.tm("switch-client", "-c", client, "-t", "work:0")
        message(s, "work:0", "Notification acknowledged.", [
            "After visiting research's agent window, its corner bell is gone.",
            "The notification in work's review tab is independent and remains.",
        ])
        cleared = renderer.terminal(s, client, "work session | research was visited")
        renderer.compose([("1 / Notification in another session", pending),
                          ("2 / Visit that window to clear it", cleared)], [
            ("Across sessions", "Local and remote-session bells stay independent.", AMBER),
        ], args.output / "across-sessions.png")

        # Same theme and same state, only placement mode changes.
        s.load("none")
        s.tm("set-option", "-g", "window-status-format", " #I #W#{E:@agent-status-window} ")
        s.tm("set-option", "-g", "window-status-current-format", " #I #W#{E:@agent-status-window} ")
        s.tm("set-option", "-g", "status-right", "#{E:@agent-status-other}")
        message(s, "work:0", "Manual mode", [
            "Put the plugin's format tokens into your own status bar.",
            "Icons inherit your theme. You control any additional accents.",
        ])
        manual = renderer.terminal(s, client, "manual mode | existing theme")
        s.load("compact")
        message(s, "work:0", "Compact preset", [
            "The same formats, with automatic placement and status accents.",
            "Your selected tab and the rest of your theme stay in place.",
        ])
        compact = renderer.terminal(s, client, "compact preset | same theme")
        renderer.compose([("Manual: place the icons yourself", manual),
                          ("Compact: add placement and accents", compact)], [
            ("One detection engine", "Choose the amount of styling the plugin adds.", TEAL),
        ], args.output / "modes.png")
    finally:
        s.close()


if __name__ == "__main__":
    main()
