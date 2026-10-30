#!/usr/bin/env python3
"""End-to-end tests using disposable tmux servers and real, drained PTYs."""
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
TMUX = os.environ.get("TMUX_BIN", shutil.which("tmux"))
PUBLIC = "#{E:@agent-status-window}"
OTHER = "#{E:@agent-status-other}"


def copy_program(destination):
    # Copy bits only: macOS refuses to copy cat's system file flags.
    shutil.copy(shutil.which("cat"), destination)
    if sys.platform == "darwin":
        # macOS kills a moved system binary until it is signed again.
        subprocess.run(["codesign", "-f", "-s", "-", str(destination)],
                       check=True, capture_output=True)


class Server:
    def __init__(self, columns=100, rows=30):
        self.columns, self.rows = columns, rows
        self.temp = tempfile.TemporaryDirectory(prefix="agent status, test-")
        self.fixture_temp = tempfile.TemporaryDirectory(prefix="agent-fixture-")
        self.socket = str(Path(self.temp.name) / "socket")
        self.env = os.environ.copy()
        self.env.pop("TMUX", None)
        self.env.pop("TMUX_PANE", None)
        self.env.update(TERM="xterm-256color", TMUX_BIN=TMUX)
        self.clients = []
        # A real executable named codex exercises tmux's process-name detection
        # without launching an AI client or overriding the recognition format.
        self.agent_program = Path(self.fixture_temp.name) / "codex"
        copy_program(self.agent_program)
        self.tm("-f", "/dev/null", "new-session", "-d", "-s", "A",
                "-x", str(columns), "-y", str(rows), "sleep 300")
        self.tm("set-option", "-g", "monitor-bell", "on")
        self.tm("set-option", "-g", "bell-action", "any")
        self.tm("set-option", "-g", "visual-bell", "on")
        self.tm("set-option", "-g", "status-interval", "1")
        self.tm("set-option", "-g", "display-time", "100")
        # A session name must not be shell-evaluated by any plugin code.
        self.tm("new-session", "-d", "-s", "B", "sleep 300")

    def tm(self, *args, check=True):
        r = subprocess.run([TMUX, "-S", self.socket, *args], env=self.env,
                           capture_output=True, text=True, timeout=8)
        if check and r.returncode:
            raise AssertionError(f"tmux {args}: {r.stderr}")
        return r.stdout.strip()

    def load(self, mode=None, check=True, via_tmux=False):
        if mode is not None:
            self.tm("set-option", "-g", "@agent-status-preset", mode)
        if via_tmux:
            # Exercise the actual manual/TPM run-shell path and TMUX socket parsing.
            return self.tm("run-shell", shlex.quote(str(ROOT / "agent-status.tmux")))
        r = subprocess.run([str(ROOT / "agent-status.tmux"), "--socket", self.socket],
                           env=self.env, capture_output=True, text=True, timeout=10)
        if check and r.returncode:
            raise AssertionError(r.stderr)
        return r

    def attach(self, target):
        old = set(self.tm("list-clients", "-F", "#{client_name}").splitlines())
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ,
                    struct.pack("HHHH", self.rows, self.columns, 0, 0))
        process = subprocess.Popen([TMUX, "-S", self.socket, "attach-session",
                                    "-t", target], env=self.env, stdin=slave,
                                   stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        output = bytearray()

        def drain():
            try:
                while True:
                    data = os.read(master, 65536)
                    if not data:
                        break
                    output.extend(data)
            except OSError:
                pass

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        self.clients.append((process, master, reader, output))
        for _ in range(50):
            names = set(self.tm("list-clients", "-F", "#{client_name}").splitlines())
            if names - old:
                return (names - old).pop()
            time.sleep(.02)
        raise AssertionError("client did not attach")

    def agent(self, target="A:1", name="codex"):
        program = Path(self.fixture_temp.name) / name
        if not program.exists():
            copy_program(program)
        command = shlex.quote(str(program))
        pane = self.tm("new-window", "-d", "-t", target, "-P", "-F", "#{pane_id}",
                       command)
        for _ in range(50):
            if self.eval(pane, "#{pane_current_command}") == name:
                break
            time.sleep(.02)
        return pane

    def emit(self, pane, data):
        tty = self.eval(pane, "#{pane_tty}")
        with open(tty, "wb", buffering=0) as stream:
            stream.write(data.encode() if isinstance(data, str) else data)
        time.sleep(.07)

    def busy(self, pane, on=True):
        self.emit(pane, f"\x1b]2;{'⠋ Working' if on else 'Finished'}\x07")

    def eval(self, target, fmt, client=None):
        args = ["display-message", "-p", "-t", target]
        if client:
            args += ["-c", client]
        return self.tm(*args, fmt)

    def option(self, key):
        return self.tm("show-options", "-gqv", key)

    def close(self):
        self.tm("kill-server", check=False)
        for process, master, reader, _ in self.clients:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=3)
            os.close(master)
            reader.join(timeout=1)
        self.temp.cleanup()
        self.fixture_temp.cleanup()


class Integration(unittest.TestCase):
    def setUp(self):
        self.s = Server()
        self.addCleanup(self.s.close)

    def test_manual_does_not_change_user_settings(self):
        before = self.s.tm("show-options", "-g")
        windows = self.s.tm("show-options", "-gw")
        keys = self.s.tm("list-keys")
        self.s.load("none", via_tmux=True)
        without_plugin = lambda value: "\n".join(
            line for line in value.splitlines() if not line.startswith("@agent-status-"))
        self.assertEqual(without_plugin(before), without_plugin(self.s.tm("show-options", "-g")))
        self.assertEqual(windows, self.s.tm("show-options", "-gw"))
        self.assertEqual(keys, self.s.tm("list-keys"))
        self.assertEqual("", self.s.eval("A:0", PUBLIC))

    def test_recognition_busy_idle_hidden_and_dead(self):
        a = self.s.agent()
        self.s.load()
        self.assertEqual("1", self.s.eval(a, "#{E:@agent-status-internal-pane}"))
        self.assertEqual("0", self.s.eval(a, "#{E:@agent-status-window-busy}"))
        self.s.busy(a)
        self.assertEqual("1", self.s.eval(a, "#{E:@agent-status-window-busy}"))
        self.assertEqual("⚙", self.s.eval(a, PUBLIC))
        self.s.tm("split-window", "-t", a, "sleep 300")
        self.s.tm("resize-pane", "-Z", "-t", "A:1")
        self.assertEqual("1", self.s.eval("A:1", "#{E:@agent-status-window-busy}"))
        self.s.busy(a, False)
        self.assertEqual("", self.s.eval(a, PUBLIC))
        self.s.busy("A:0")
        self.assertEqual("0", self.s.eval("A:0", "#{E:@agent-status-window-busy}"))
        self.s.tm("set-option", "-w", "-t", a, "remain-on-exit", "on")
        self.s.busy(a)
        self.s.tm("send-keys", "-t", a, "C-d")
        for _ in range(50):
            if self.s.eval(a, "#{pane_dead}") == "1":
                break
            time.sleep(.02)
        self.assertEqual("1", self.s.eval(a, "#{pane_dead}"))
        self.assertEqual("0", self.s.eval(a, "#{E:@agent-status-window-busy}"))

        for index, name in enumerate(("claude", "agy"), start=2):
            with self.subTest(agent=name):
                pane = self.s.agent(f"A:{index}", name=name)
                self.assertEqual("1", self.s.eval(pane, "#{E:@agent-status-internal-pane}"))
                self.assertEqual("", self.s.eval(pane, PUBLIC))
                self.s.busy(pane)
                self.assertEqual("⚙", self.s.eval(pane, PUBLIC))
                self.s.busy(pane, False)
                self.assertEqual("", self.s.eval(pane, PUBLIC))

    def test_claude_static_title_activity_and_stale_state(self):
        a = self.s.agent(name="claude")
        client = self.s.attach("B:0")
        self.s.load("compact")
        self.s.emit(a, "\x1b]2;✳ Claude Code\x07")
        self.assertEqual("0", self.s.eval(a, "#{E:@agent-status-window-busy}"))
        self.s.tm("set-option", "-p", "-t", a, "@agent-status-busy-command", "claude")
        self.assertEqual("⚙", self.s.eval(a, PUBLIC))
        self.assertIn("⚙", self.s.eval("B:0", OTHER, client))
        self.assertIn("bg=#30464b", self.s.eval(a, "#{E:window-status-format}"))
        self.s.load()  # Reloads must not clear an active turn.
        self.assertEqual("⚙", self.s.eval(a, PUBLIC))
        self.s.emit(a, "\a")
        self.s.tm("set-option", "-p", "-t", a, "@agent-status-busy-command", "")
        self.assertEqual("0", self.s.eval(a, "#{E:@agent-status-window-busy}"))
        self.assertIn("🔔", self.s.eval("B:0", OTHER, client))
        self.assertNotIn("⚙", self.s.eval("B:0", OTHER, client))
        # A hard-killed Claude may leave its option behind. It must not mark
        # another command as working, even if the old title is still present.
        self.s.tm("set-option", "-p", "-t", a, "@agent-status-busy-command", "claude")
        self.s.tm("respawn-pane", "-k", "-t", a, "sleep 300")
        self.assertEqual("0", self.s.eval(a, "#{E:@agent-status-window-busy}"))

    def test_antigravity_title_adapter(self):
        a = self.s.agent(name="agy")
        client = self.s.attach("B:0")
        self.s.load("compact")
        script = ROOT / "adapters" / "antigravity" / "title.py"
        cases = [
            (json.dumps({"agent_state": state, "conversation_title": "private"}), busy)
            for state, busy in [
                ("idle", False), ("working", True), ("tool_use", True),
                ("reviewing", False), ("working", True), ("error", False),
                ("initializing", False), ("authenticating", False),
                ("future-state", False),
            ]
        ] + [("{}", False), ("null", False), ("[]", False), ("not JSON", False)]
        for payload, busy in cases:
            with self.subTest(payload=payload):
                result = subprocess.run([sys.executable, str(script)], input=payload,
                                        capture_output=True, text=True, check=True, timeout=5)
                self.assertEqual("", result.stderr)
                self.assertEqual("⠋ agy\n" if busy else "agy\n", result.stdout)
                self.s.emit(a, f"\x1b]2;{result.stdout.strip()}\x07")
                self.assertEqual("⚙" if busy else "", self.s.eval(a, PUBLIC))
                self.assertEqual(busy, "⚙" in self.s.eval("B:0", OTHER, client))
                self.assertEqual("0", self.s.eval(a, "#{window_bell_flag}"))
        self.s.emit(a, "\a")
        self.assertEqual("🔔", self.s.eval(a, PUBLIC))
        self.assertIn("🔔", self.s.eval("B:0", OTHER, client))

    def test_claude_under_launcher_reports_its_own_command(self):
        # Launchers such as toolbox-exec stay in the foreground instead of claude.
        a = self.s.agent(name="toolbox-exec")
        self.s.load("compact")
        self.s.emit(a, "\x1b]2;✳ Claude Code\x07")
        self.s.tm("set-option", "-p", "-F", "-t", a, "@agent-status-busy-command",
                  "#{pane_current_command}")
        self.assertEqual("⚙", self.s.eval(a, PUBLIC))
        self.s.tm("set-option", "-p", "-t", a, "@agent-status-busy-command", "")
        self.assertEqual("", self.s.eval(a, PUBLIC))

    def test_cross_session_bells_survive_completion_and_reload(self):
        a1 = self.s.agent()
        a2 = self.s.agent("A:2")
        self.s.tm("split-window", "-t", a1, "sleep 300")
        client = self.s.attach("A:1")
        self.s.load("compact")
        self.s.tm("switch-client", "-c", client, "-t", "B")
        self.s.busy(a1)
        self.assertIn("⚙", self.s.eval("B:0", OTHER, client))
        self.s.emit(a1, "\a")
        self.assertIn("🔔", self.s.eval("B:0", OTHER, client))
        self.assertEqual("🔔", self.s.eval(a1, PUBLIC))
        self.s.emit(a1, "Worked for 20m 58s • 9:19 PM\r\n")
        self.s.busy(a1, False)
        time.sleep(.2)  # Past this test server's popup timeout.
        self.s.load()
        self.assertIn("🔔", self.s.eval("B:0", OTHER, client))
        self.assertNotIn("⚙", self.s.eval("B:0", OTHER, client))
        self.s.emit(a2, "\a")
        self.s.tm("switch-client", "-c", client, "-t", "A:1")
        self.s.tm("switch-client", "-c", client, "-t", "B")
        self.assertIn("🔔", self.s.eval("B:0", OTHER, client))
        self.s.tm("switch-client", "-c", client, "-t", "A:2")
        self.s.tm("switch-client", "-c", client, "-t", "B")
        self.assertNotIn("🔔", self.s.eval("B:0", OTHER, client))
        # Verify actual PTY output as well as evaluated formats.
        self.assertIn("🔔".encode(), self.s.clients[0][3])

    def test_two_clients_and_session_rename(self):
        a = self.s.agent()
        b = self.s.agent("B:1")
        ca = self.s.attach("A:0")
        cb = self.s.attach("B:0")
        self.s.load()
        self.s.busy(a)
        self.assertEqual("", self.s.eval("A:0", OTHER, ca))
        self.assertIn("⚙", self.s.eval("B:0", OTHER, cb))
        self.s.tm("rename-session", "-t", "A", "Renamed A")
        self.assertIn("⚙", self.s.eval("B:0", OTHER, cb))
        self.s.emit(b, "\a")
        self.assertIn("🔔", self.s.eval("Renamed A:0", OTHER, ca))
        self.assertNotIn("🔔", self.s.eval("B:0", OTHER, cb))
        self.s.tm("move-window", "-s", "Renamed A:1", "-t", "B:2")
        self.assertNotIn("⚙", self.s.eval("B:0", OTHER, cb))

    def test_compact_reload_disable_and_later_edits(self):
        originals = {key: self.s.option(key) for key in
                     ("window-status-format", "window-status-current-format", "status-right")}
        self.s.load("compact")
        applied = {key: self.s.option(key) for key in originals}
        self.s.load()
        self.assertEqual(applied, {key: self.s.option(key) for key in originals})
        # Simulate a later plugin appending a shell expression.
        addition = '#(printf saved) PREFIX'
        self.s.tm("set-option", "-g", "status-right", applied["status-right"] + addition)
        self.s.load()
        self.s.load("none")
        originals["status-right"] += addition
        self.assertEqual(originals, {key: self.s.option(key) for key in originals})
        self.s.load("compact")
        self.s.tm("set-option", "-g", "window-status-format", "NEW THEME #W")
        self.s.load()
        self.s.load("none")
        self.assertEqual("NEW THEME #W", self.s.option("window-status-format"))

    def test_compact_tints_inline_powerline_themes(self):
        arrow = "\ue0b0"
        theme = (f"#[fg=#1e2030,bg=#363a4f]{arrow}#[fg=#8bd5ca,bg=#363a4f,bold] #I:#W#F "
                 f"#[fg=#363a4f,bg=#1e2030,none]{arrow}")
        current = f"#[fg=#181926,bg=#8bd5ca,bold] #I:#W#F #[fg=#8bd5ca,bg=#1e2030,none]{arrow}"
        self.s.tm("set-option", "-g", "window-status-format", theme)
        self.s.tm("set-option", "-g", "window-status-current-format", current)
        a = self.s.agent()
        self.s.load("compact")
        idle = self.s.eval(a, "#{E:window-status-format}")
        self.assertIn(f"bg=#363a4f]{arrow}", idle)
        self.assertNotIn("#30464b", idle)
        self.s.busy(a)
        busy = self.s.eval(a, "#{E:window-status-format}")
        # Body, entry and exit separators follow the accent (plus the wrapper).
        self.assertNotIn("#363a4f", busy)
        self.assertEqual(4, busy.count("#30464b"))
        self.assertIn("fg=#cad3f5,bg=#30464b,bold] 1:codex", busy)
        # The icon stays inside the tab, before the closing separator.
        self.assertIn(f"1:codex ⚙ #[fg=#30464b,bg=#1e2030,none]{arrow}#[default]", busy)
        self.s.emit(a, "\a")
        bell = self.s.eval(a, "#{E:window-status-format}")
        self.assertEqual(4, bell.count("#eed49f"))
        self.assertNotIn("#30464b", bell)
        self.assertIn(" 🔔 #[", bell)
        self.s.tm("select-window", "-t", "A:1")
        selected = self.s.eval(a, "#{E:window-status-current-format}")
        self.assertIn("bg=#8bd5ca,bold] 1:codex", selected)
        self.assertNotIn("#30464b", selected)
        applied = self.s.option("window-status-format")
        self.s.load()
        self.assertEqual(applied, self.s.option("window-status-format"))
        self.s.load("none")
        self.assertEqual(theme, self.s.option("window-status-format"))
        self.assertEqual(current, self.s.option("window-status-current-format"))

    def test_compact_icon_falls_back_to_the_end(self):
        # A closing style inside a conditional is not a safe insertion point.
        theme = "#[bg=#363a4f] #W#{?window_bell_flag,#[bg=red] BELL,}"
        self.s.tm("set-option", "-g", "window-status-format", theme)
        self.s.load("compact")
        self.assertTrue(self.s.option("window-status-format").endswith(
            "#{E:@agent-status-internal-preset-window-icon}"
            "#{E:@agent-status-internal-preset-window-close}"))
        self.s.load("none")
        self.assertEqual(theme, self.s.option("window-status-format"))

    def test_existing_manual_tokens_and_empty_overrides(self):
        self.s.tm("set-option", "-g", "window-status-format", f"#W {PUBLIC}")
        self.s.tm("set-option", "-g", "status-right", f"CLOCK {OTHER}")
        self.s.tm("set-option", "-g", "@agent-status-running-style", "")
        self.s.load("compact")
        self.assertEqual("", self.s.option("@agent-status-internal-running-style"))
        self.assertEqual(1, self.s.option("window-status-format").count(PUBLIC))
        self.assertNotIn("preset-window-icon", self.s.option("window-status-format"))
        self.assertEqual(f"CLOCK {OTHER}", self.s.option("status-right"))
        self.s.load("none")
        self.assertEqual(f"#W {PUBLIC}", self.s.option("window-status-format"))
        self.s.tm("set-option", "-gu", "@agent-status-running-style")
        self.s.load("compact")
        self.assertIn("#30464b", self.s.option("@agent-status-internal-running-style"))
        self.s.load("none")
        self.assertEqual("", self.s.option("@agent-status-internal-running-style"))

    def test_custom_layout_and_damaged_token_are_preserved(self):
        self.s.tm("set-option", "-g", "status-format[0]", "CUSTOM #S")
        before = self.s.option("status-right")
        result = self.s.load("compact")
        self.assertIn("custom status-format", result.stderr)
        self.assertEqual(before, self.s.option("status-right"))
        value = "USER #{E:@agent-status-internal-preset-EDITED}"
        self.s.tm("set-option", "-g", "status-right", value)
        result = self.s.load("none")
        self.assertIn("damaged token", result.stderr)
        self.assertEqual(value, self.s.option("status-right"))

    def test_config_values_are_data_and_regexes_are_validated(self):
        a = self.s.agent()
        marker = Path(self.s.temp.name) / "must-not-exist"
        icon = f"R,'$(touch {marker})`touch {marker}` #{{literal}}"
        self.s.tm("set-option", "-g", "@agent-status-running-icon", icon)
        self.s.tm("set-option", "-g", "@agent-status-busy-title-pattern", r"^Busy, 'quoted' ")
        self.s.load()
        self.s.emit(a, "\x1b]2;Busy, 'quoted' task\x07")
        self.assertEqual("1", self.s.eval(a, "#{E:@agent-status-window-busy}"))
        self.assertEqual(icon, self.s.eval(a, PUBLIC))
        self.assertFalse(marker.exists())
        self.s.tm("set-option", "-g", "@agent-status-command-pattern", "[")
        before = self.s.tm("show-options", "-g")
        result = self.s.load(check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.s.tm("show-options", "-g"))

    def test_preset_styles_and_idle_empty_output(self):
        a = self.s.agent()
        self.s.load("compact")
        self.s.busy(a)
        value = self.s.eval(a, "#{E:window-status-format}")
        self.assertIn("#30464b", value)
        self.s.tm("select-window", "-t", "A:1")
        value = self.s.eval(a, "#{E:window-status-current-format}")
        self.assertNotIn("#30464b", value)
        self.s.tm("select-window", "-t", "A:0")
        self.s.emit(a, "\a")
        value = self.s.eval(a, "#{E:window-status-format}")
        self.assertIn("#eed49f", value)
        self.assertNotIn("#30464b", value)
        self.assertEqual("", self.s.eval("A:0", PUBLIC))

    def test_current_window_bells_follow_native_acknowledgment(self):
        a = self.s.agent()
        c = self.s.attach("A:1")
        self.s.load()
        self.s.emit(a, "\a")
        self.assertEqual("0", self.s.eval(a, "#{E:@agent-status-window-bell}", c))
        self.s.tm("detach-client", "-t", c)
        self.s.emit(a, "\a")
        self.assertEqual("1", self.s.eval(a, "#{E:@agent-status-window-bell}"))
        self.s.attach("A:1")
        self.assertEqual("0", self.s.eval(a, "#{E:@agent-status-window-bell}"))

    def test_corner_restores_neighboring_text_style_in_terminal(self):
        a = self.s.agent()
        c = self.s.attach("B:0")
        self.s.tm("set-option", "-g", "status-style", "bg=colour17,fg=colour250")
        self.s.tm("set-option", "-g", "status-right",
                  f"#[fg=colour46]HEAD {OTHER} TAIL")
        self.s.tm("set-option", "-g", "status-right-length", "80")
        self.s.tm("set-option", "-g", "@agent-status-bell-style",
                  "bg=colour172,fg=colour16,bold")
        self.s.load()
        self.s.emit(a, "\a")
        self.s.tm("clear-history", "-t", "B:0")
        start = len(self.s.clients[0][3])
        self.s.tm("refresh-client", "-R", "-t", c)
        time.sleep(.15)
        data = bytes(self.s.clients[0][3][start:])
        # Track terminal SGR colors/weight where unique neighboring labels render.
        style = {"fg": None, "bg": None, "bold": False}
        labels = {}
        previous = 0
        for match in re.finditer(rb"\x1b\[([0-9;]*)m", data):
            chunk = data[previous:match.start()]
            for label in (b"HEAD", b"TAIL"):
                if label in chunk:
                    labels[label] = style.copy()
            values = [int(v or b"0") for v in match[1].split(b";")]
            i = 0
            while i < len(values):
                v = values[i]
                if v == 0:
                    style = {"fg": None, "bg": None, "bold": False}
                elif v == 1:
                    style["bold"] = True
                elif v == 22:
                    style["bold"] = False
                elif v in (38, 48) and values[i + 1:i + 2] == [5]:
                    style["fg" if v == 38 else "bg"] = values[i + 2]
                    i += 2
                elif 30 <= v <= 37:
                    style["fg"] = v - 30
                elif 40 <= v <= 47:
                    style["bg"] = v - 40
                elif v in (39, 49):
                    style["fg" if v == 39 else "bg"] = None
                i += 1
            previous = match.end()
        for label in (b"HEAD", b"TAIL"):
            if label in data[previous:]:
                labels[label] = style.copy()
        self.assertEqual({b"HEAD", b"TAIL"}, set(labels), repr(data))
        self.assertEqual(labels[b"HEAD"], labels[b"TAIL"])
        self.assertEqual(46, labels[b"TAIL"]["fg"])

    def test_linked_window_bell_acknowledged_by_another_client(self):
        a = self.s.agent()
        self.s.tm("link-window", "-s", "A:1", "-t", "B:1")
        ca = self.s.attach("A:0")
        self.s.attach("B:0")
        self.s.load()
        self.s.emit(a, "\a")
        self.assertEqual("1", self.s.eval("B:1", "#{E:@agent-status-window-bell}"))
        self.s.tm("switch-client", "-c", ca, "-t", "A:1")
        self.assertEqual("0", self.s.eval("B:1", "#{E:@agent-status-window-bell}"))


if __name__ == "__main__":
    print(f"Testing {ROOT} with {subprocess.check_output([TMUX, '-V'], text=True).strip()}",
          flush=True)
    unittest.main(verbosity=2)
