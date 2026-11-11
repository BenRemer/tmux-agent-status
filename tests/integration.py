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
BELL = "\uf0f3"  # Default Nerd Font bell
STALE = "\uf127"  # Default Nerd Font stale-relay icon
RUNNING_BG = "#30464b"  # The compact preset's running accent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from themes import THEMES  # noqa: E402


def render_cells(expanded):
    """(char, bg) for each visible character of an expanded tmux format.

    Follows the style rules the preset relies on: bg=/fg=, default,
    push-default/pop-default, reverse and none. Unset colors are None.
    """
    cells = []
    fg = bg = base_fg = base_bg = None
    reverse = False
    for style, text in re.findall(r"#\[([^]]*)\]|([^#]+|#)", expanded):
        if text:
            cells += [(ch, fg if reverse else bg) for ch in text]
            continue
        for item in re.split(r"[ ,]+", style):
            if item.startswith("bg="):
                bg = None if item[3:] == "default" else item[3:]
            elif item.startswith("fg="):
                fg = None if item[3:] == "default" else item[3:]
            elif item == "default":
                fg, bg = base_fg, base_bg
            elif item == "push-default":
                base_fg, base_bg = fg, bg
            elif item == "pop-default":
                base_fg = base_bg = None
            elif item == "reverse":
                reverse = True
            elif item in ("none", "noreverse"):
                reverse = False
    return cells


_FIXTURE_TEMP = None
_FIXTURE_SOURCE = None


def copy_program(destination):
    global _FIXTURE_TEMP, _FIXTURE_SOURCE
    # Copy a stdin-reading binary under the agent's name so tmux sees a real
    # foreground process name. Ubuntu 26's uutils cat is a multicall binary that
    # rejects unknown argv[0] names, so probe before caching a candidate.
    candidates = (_FIXTURE_SOURCE,) if _FIXTURE_SOURCE else ("cat", "gnucat", "rev")
    for candidate in candidates:
        source = shutil.which(candidate) if candidate else None
        if not source:
            continue
        # Copy bits only: macOS refuses to copy system file flags.
        shutil.copy(source, destination)
        if sys.platform == "darwin":
            # macOS kills a moved system binary until it is signed again.
            subprocess.run(["codesign", "-f", "-s", "-", str(destination)],
                           check=True, capture_output=True)
        if _FIXTURE_SOURCE:
            return
        if subprocess.run([str(destination)], input=b"",
                          capture_output=True, timeout=2).returncode == 0:
            _FIXTURE_SOURCE = os.path.realpath(source)
            return
    _FIXTURE_TEMP = tempfile.TemporaryDirectory(prefix="agent-fixture-src-")
    _FIXTURE_SOURCE = str(Path(_FIXTURE_TEMP.name) / "agent-fixture")
    subprocess.run(
        ["cc", "-x", "c", "-", "-o", _FIXTURE_SOURCE],
        input="#include <unistd.h>\n"
              "int main(void){char b[256];while(read(0,b,sizeof b)>0){}return 0;}\n",
        text=True, check=True, capture_output=True)
    shutil.copy(_FIXTURE_SOURCE, destination)


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
        # Most tests toggle titles freely; the completion bell has its own test.
        self.tm("set-option", "-g", "@agent-status-completion-bell", "off")
        # A session name must not be shell-evaluated by any plugin code.
        self.tm("new-session", "-d", "-s", "B", "sleep 300")

    def tm(self, *args, check=True):
        r = subprocess.run([TMUX, "-S", self.socket, *args], env=self.env,
                           capture_output=True, text=True, timeout=8)
        if check and r.returncode:
            raise AssertionError(f"tmux {args}: {r.stderr}")
        return r.stdout.strip()

    def load(self, mode=None, check=True, via_tmux=False, real_clock=False):
        if mode is not None:
            self.tm("set-option", "-g", "@agent-status-preset", mode)
        if via_tmux:
            # Exercise the actual manual/TPM run-shell path and TMUX socket parsing.
            r = self.tm("run-shell", shlex.quote(str(ROOT / "agent-status.tmux")))
        else:
            r = subprocess.run([str(ROOT / "agent-status.tmux"), "--socket", self.socket],
                               env=self.env, capture_output=True, text=True, timeout=10)
            if check and r.returncode:
                raise AssertionError(r.stderr)
        if not real_clock:
            # The relay clock is a #() job, and display-message never runs
            # jobs. Formats evaluated here read the time directly instead.
            self.tm("set-option", "-g", "@agent-status-internal-clock",
                    "#{T:@agent-status-internal-now}")
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
                return pane
            time.sleep(.02)
        try:
            probe = subprocess.run([str(program)], input="", capture_output=True,
                                   text=True, timeout=2)
            probe = f"exit {probe.returncode}: {probe.stdout}{probe.stderr}"
        except Exception as error:  # Report the cause instead of the symptom.
            probe = repr(error)
        raise AssertionError(
            f"{name} did not start in {pane}; source is {_FIXTURE_SOURCE}; run directly: {probe}")

    def emit(self, pane, data):
        tty = self.eval(pane, "#{pane_tty}")
        if not tty:
            state = self.tm("list-panes", "-a", "-F",
                            "#{pane_id} #{session_name}:#{window_index} dead=#{pane_dead} "
                            "status=#{pane_dead_status} cmd=#{pane_current_command} "
                            "start=#{pane_start_command}")
            raise AssertionError(f"pane {pane} has no tty:\n{state}")
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

    def raw_option(self, key):
        # tm() strips whitespace, which is part of a format's padding.
        # #{option} inserts the value without expanding it.
        return self.eval("A:0", f"[#{{{key}}}]")[1:-1]

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

    def wait_for(self, target, fmt, expected):
        for _ in range(50):
            if self.s.eval(target, fmt) == expected:
                break
            time.sleep(.02)
        return self.s.eval(target, fmt)

    def test_completion_bell_from_busy_title(self):
        self.s.tm("set-option", "-g", "@agent-status-completion-bell", "on")
        self.s.load()
        a = self.s.agent()
        bell = "#{window_bell_flag}"
        # Every spinner frame is a title change; none of them rings.
        self.s.busy(a)
        self.s.emit(a, "\x1b]2;⠙ Working\x07")
        time.sleep(.2)
        self.assertEqual("0", self.s.eval(a, bell))
        # The marker records when the turn started.
        self.assertRegex(self.s.eval(a, "#{@agent-status-internal-title-busy}"), r"^[0-9]{10,}$")
        self.s.busy(a, False)
        self.assertEqual("1", self.wait_for(a, bell, "1"))
        self.assertEqual("", self.s.eval(a, "#{@agent-status-internal-title-busy}"))
        # A second idle title does not ring again.
        self.s.tm("select-window", "-t", a)
        self.s.tm("select-window", "-t", "A:0")
        self.s.busy(a, False)
        time.sleep(.2)
        self.assertEqual("0", self.s.eval(a, bell))

    def test_completion_bell_skips_the_window_being_viewed(self):
        self.s.tm("set-option", "-g", "@agent-status-completion-bell", "on")
        # Forward bells to the terminal, as bell-action any does by default.
        self.s.tm("set-option", "-g", "visual-bell", "off")
        self.s.load()
        a = self.s.agent()
        self.s.attach("A:1")
        output = self.s.clients[-1][3]
        time.sleep(.3)
        start = len(output)
        # Like an agent's startup spinner, in the window you are looking at.
        self.s.busy(a)
        self.s.busy(a, False)
        time.sleep(.4)
        sent = re.sub(rb"\x1b\][^\x07]*\x07", b"", bytes(output[start:]))
        self.assertNotIn(b"\x07", sent)
        self.assertEqual("", self.s.eval(a, "#{@agent-status-internal-title-busy}"))
        # The same transition in a window you are not viewing still rings.
        self.s.tm("select-window", "-t", "A:0")
        self.s.busy(a)
        self.s.busy(a, False)
        self.assertEqual("1", self.wait_for(a, "#{window_bell_flag}", "1"))

    def test_completion_bell_rings_the_viewed_window_after_a_long_turn(self):
        # Nested in an outer tmux, the window this server shows may not be the
        # one you are looking at; tmux passes a real turn's bell on to it.
        self.s.tm("set-option", "-g", "@agent-status-completion-bell", "on")
        self.s.tm("set-option", "-g", "visual-bell", "off")
        self.s.tm("set-option", "-g", "@agent-status-viewed-bell-seconds", "1")
        self.s.load()
        a = self.s.agent()
        self.s.attach("A:1")
        output = self.s.clients[-1][3]
        time.sleep(.3)
        start = len(output)
        self.s.busy(a)
        time.sleep(1.2)
        self.s.busy(a, False)
        time.sleep(.4)
        sent = re.sub(rb"\x1b\][^\x07]*\x07", b"", bytes(output[start:]))
        self.assertIn(b"\x07", sent)

    def test_bell_seconds_options(self):
        for name, default in (("followup", "30"), ("viewed", "10")):
            option = f"@agent-status-{name}-bell-seconds"
            key = f"@agent-status-internal-{name}-bell-seconds"
            self.s.load()
            self.assertEqual(default, self.s.option(key))
            self.s.tm("set-option", "-g", option, "0")
            self.s.load()
            self.assertEqual("0", self.s.option(key))
            self.s.tm("set-option", "-g", option, "soon")
            r = self.s.load(check=False)
            self.assertNotEqual(0, r.returncode)
            self.assertIn("whole numbers", r.stderr)
            self.s.tm("set-option", "-gu", option)

    def test_completion_bell_skips_titles_from_non_agents(self):
        self.s.tm("set-option", "-g", "@agent-status-completion-bell", "on")
        self.s.load()
        self.s.tm("new-window", "-d", "-t", "A:1", "sleep 300")
        self.s.busy("A:1")
        self.s.busy("A:1", False)
        time.sleep(.2)
        self.assertEqual("0", self.s.eval("A:1", "#{window_bell_flag}"))

    def test_completion_bell_off_removes_the_hook(self):
        self.s.tm("set-option", "-g", "@agent-status-completion-bell", "on")
        self.s.load()
        self.assertIn("pane-title-changed", self.s.tm("show-hooks", "-g", "pane-title-changed"))
        self.s.tm("set-option", "-g", "@agent-status-completion-bell", "off")
        self.s.load()
        self.assertNotIn("[4721]", self.s.tm("show-hooks", "-g", "pane-title-changed"))

    def test_uninstall_removes_everything_the_plugin_set(self):
        formats = {key: self.s.option(key) for key in
                   ("window-status-format", "window-status-current-format", "status-right")}
        self.s.tm("set-option", "-g", "@agent-status-completion-bell", "on")
        self.s.tm("set-option", "-g", "@agent-status-relay", "on")
        titles = self.s.option("set-titles-string")
        a = self.s.agent()
        self.s.load("compact")
        self.assertNotEqual(titles, self.s.option("set-titles-string"))
        self.s.busy(a)
        self.s.tm("set-option", "-p", "-t", a, "@agent-status-busy-command", "codex")
        r = subprocess.run([str(ROOT / "agent-status.tmux"), "--socket", self.s.socket,
                            "--uninstall"], env=self.s.env, capture_output=True, text=True,
                           timeout=10)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(formats, {key: self.s.option(key) for key in formats})
        self.assertNotIn("@agent-status", self.s.tm("show-options", "-g"))
        self.assertNotIn("[4721]", self.s.tm("show-hooks", "-g", "pane-title-changed"))
        self.assertNotIn("@agent-status", self.s.tm("show-options", "-p", "-t", a))
        self.assertEqual(titles, self.s.option("set-titles-string"))
        self.assertEqual("off", self.s.option("set-titles"))

    def relay_title(self, busy, total, age=0, bells=None):
        unread = "" if bells is None else f" !{bells}"
        return f"agents {busy}/{total}{unread} ~{int(time.time()) - age}"

    def test_relay_publishes_session_agents_and_restores_titles(self):
        self.s.tm("set-option", "-g", "set-titles-string", "DEV #S")
        self.s.tm("set-option", "-g", "@agent-status-relay", "on")
        self.s.load()
        title = "#{T:set-titles-string}"
        self.assertEqual("on", self.s.option("set-titles"))
        # Without agents the user's own title is used.
        self.assertEqual("DEV A", self.s.eval("A:0", title))
        a = self.s.agent()
        self.assertRegex(self.s.eval("A:0", title), r"^agents 0/1 !0 ~[0-9]+$")
        self.s.busy(a)
        busy = self.s.eval("A:0", title)
        self.assertRegex(busy, r"^agents 1/1 !0 ~[0-9]+$")
        self.assertLess(abs(int(busy.split("~")[1]) - time.time()), 5)
        # The relay covers the whole server, including other sessions' bells.
        self.s.tm("new-window", "-d", "-t", "B:5", "sleep 300")
        self.s.emit("B:5", "\a")
        self.assertRegex(self.s.eval("B:0", title), r"^agents 1/1 !1 ~[0-9]+$")
        self.s.load()
        self.assertEqual("DEV #S", self.s.option("@agent-status-internal-relay-fallback"))
        self.s.tm("set-option", "-g", "@agent-status-relay", "off")
        self.s.load()
        self.assertEqual("DEV #S", self.s.option("set-titles-string"))
        self.assertEqual("off", self.s.option("set-titles"))

    def test_relay_keeps_non_ascii_titles_without_a_utf8_locale(self):
        original = "✳ #S ⠋"
        self.s.tm("set-option", "-g", "set-titles-string", original)
        self.s.tm("set-option", "-g", "@agent-status-relay", "on")
        env = {k: v for k, v in self.s.env.items() if k not in ("LC_ALL", "LC_CTYPE", "LANG")}
        env["LANG"] = "C"
        for relay in ("on", "off"):
            self.s.tm("set-option", "-g", "@agent-status-relay", relay)
            r = subprocess.run([str(ROOT / "agent-status.tmux"), "--socket", self.s.socket],
                               env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(original, self.s.raw_option("set-titles-string"))

    def test_relay_tab_shows_running_stale_and_bell(self):
        a = self.s.agent(name="ssh")
        self.s.load("compact")
        self.s.emit(a, f"\x1b]2;{self.relay_title(1, 2)}\x07")
        self.assertEqual("⚙", self.s.eval(a, PUBLIC))
        self.assertEqual("1", self.s.eval(a, "#{E:@agent-status-window-busy}"))
        self.assertIn("⚙", self.s.eval("B:0", OTHER))
        self.s.emit(a, f"\x1b]2;{self.relay_title(0, 2)}\x07")
        self.assertEqual("", self.s.eval(a, PUBLIC))
        # The count is opt-in.
        self.s.tm("set-option", "-g", "@agent-status-relay-count", "on")
        self.s.load()
        self.s.emit(a, f"\x1b]2;{self.relay_title(2, 3)}\x07")
        self.assertEqual("⚙ 2/3", self.s.eval(a, PUBLIC))
        # A relay title older than 30 seconds is stale, in the tab and corner.
        self.s.emit(a, f"\x1b]2;{self.relay_title(2, 3, age=31)}\x07")
        self.assertEqual(STALE, self.s.eval(a, PUBLIC))
        self.assertEqual("0", self.s.eval(a, "#{E:@agent-status-window-busy}"))
        self.assertIn(STALE, self.s.eval("B:0", OTHER))
        self.assertIn("#4b3036", self.s.eval(a, "#{E:window-status-format}"))
        # A remote with unread bells gives the tab a bell while the relay is live.
        self.s.emit(a, f"\x1b]2;{self.relay_title(1, 3, bells=2)}\x07")
        self.assertEqual(BELL, self.s.eval(a, PUBLIC))
        self.assertEqual("0", self.s.eval(a, "#{window_bell_flag}"))
        self.assertIn(BELL, self.s.eval("B:0", OTHER))
        self.s.emit(a, f"\x1b]2;{self.relay_title(1, 3, bells=0)}\x07")
        self.assertEqual("⚙ 1/3", self.s.eval(a, PUBLIC))
        self.s.emit(a, f"\x1b]2;{self.relay_title(1, 3, age=31, bells=2)}\x07")
        self.assertEqual(STALE, self.s.eval(a, PUBLIC))
        # A native bell takes the tab; the corner shows both.
        self.s.emit(a, "\a")
        self.assertEqual(BELL, self.s.eval(a, PUBLIC))
        corner = self.s.eval("B:0", OTHER)
        self.assertIn(STALE, corner)
        self.assertIn(BELL, corner)
        self.assertLess(corner.index(STALE), corner.index(BELL))

    def test_relay_clock_job_renders_in_the_status_line(self):
        self.s.load(real_clock=True)
        self.s.tm("set-option", "-g", "status-right", "[#{E:@agent-status-internal-clock}]")
        self.s.attach("A:0")
        output = self.s.clients[-1][3]
        for _ in range(60):
            found = re.findall(rb"\[([0-9]{10,})\]", bytes(output))
            if found:
                break
            time.sleep(.1)
        self.assertTrue(found, bytes(output)[-300:])
        self.assertLess(abs(int(found[-1]) - time.time()), 5)

    def test_relay_title_is_ignored_outside_ssh(self):
        a = self.s.agent()  # codex, not ssh
        self.s.load()
        self.s.tm("new-window", "-d", "-t", "A:2", "sleep 300")
        self.s.emit("A:2", f"\x1b]2;{self.relay_title(1, 1)}\x07")
        self.assertEqual("", self.s.eval("A:2", PUBLIC))
        self.s.emit(a, f"\x1b]2;{self.relay_title(1, 1)}\x07")
        self.assertEqual("", self.s.eval(a, PUBLIC))

    def test_relay_end_to_end_through_a_nested_client(self):
        inner = Server()
        self.addCleanup(inner.close)
        inner.tm("set-option", "-g", "@agent-status-relay", "on")
        inner.load()
        agent = inner.agent()
        inner.busy(agent)
        # The outer pane runs a real tmux client of the inner server, as ssh would.
        self.s.tm("set-option", "-g", "@agent-status-relay-command-pattern", "^(ssh|tmux)$")
        self.s.load()
        attach = f"env -u TMUX TERM=xterm-256color {shlex.quote(TMUX)} -S {shlex.quote(inner.socket)} attach -t A"
        outer = self.s.tm("new-window", "-d", "-t", "A:3", "-P", "-F", "#{pane_id}", attach)
        public = "#{E:@agent-status-window}"
        for _ in range(100):
            if self.s.eval(outer, public) == "⚙":
                break
            time.sleep(.05)
        self.assertRegex(self.s.eval(outer, "#{pane_title}"), r"^agents 1/1 !0 ~[0-9]+$")
        self.assertEqual("⚙", self.s.eval(outer, public))
        inner.busy(agent, False)
        for _ in range(100):
            if self.s.eval(outer, public) == "":
                break
            time.sleep(.05)
        self.assertEqual("", self.s.eval(outer, public))
        # A bell in another inner session never reaches the client as a real
        # bell; the relay carries it.
        inner.emit("B:0", "\a")
        for _ in range(100):
            if self.s.eval(outer, public) == BELL:
                break
            time.sleep(.05)
        self.assertEqual(BELL, self.s.eval(outer, public))

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
        self.assertIn(BELL, self.s.eval("B:0", OTHER, client))
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
        self.assertEqual(BELL, self.s.eval(a, PUBLIC))
        self.assertIn(BELL, self.s.eval("B:0", OTHER, client))

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
        self.assertIn(BELL, self.s.eval("B:0", OTHER, client))
        self.assertEqual(BELL, self.s.eval(a1, PUBLIC))
        self.s.emit(a1, "Worked for 20m 58s • 9:19 PM\r\n")
        self.s.busy(a1, False)
        time.sleep(.2)  # Past this test server's popup timeout.
        self.s.load()
        self.assertIn(BELL, self.s.eval("B:0", OTHER, client))
        self.assertNotIn("⚙", self.s.eval("B:0", OTHER, client))
        self.s.emit(a2, "\a")
        self.s.tm("switch-client", "-c", client, "-t", "A:1")
        self.s.tm("switch-client", "-c", client, "-t", "B")
        self.assertIn(BELL, self.s.eval("B:0", OTHER, client))
        self.s.tm("switch-client", "-c", client, "-t", "A:2")
        self.s.tm("switch-client", "-c", client, "-t", "B")
        self.assertNotIn(BELL, self.s.eval("B:0", OTHER, client))
        # Verify actual PTY output as well as evaluated formats.
        self.assertIn(BELL.encode(), self.s.clients[0][3])

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
        self.assertIn(BELL, self.s.eval("Renamed A:0", OTHER, ca))
        self.assertNotIn(BELL, self.s.eval("B:0", OTHER, cb))
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
        # tmux may automatically rename the window, so match only its index.
        self.assertIn("fg=#cad3f5,bg=#30464b,bold] 1:", busy)
        # The icon stays inside the tab, before the closing separator.
        self.assertRegex(busy, f" ⚙ #\\[fg=#30464b,bg=#1e2030,none\\]{arrow}#\\[default\\]")
        self.s.emit(a, "\a")
        bell = self.s.eval(a, "#{E:window-status-format}")
        self.assertEqual(4, bell.count("#eed49f"))
        self.assertNotIn("#30464b", bell)
        self.assertIn(f" {BELL} #[", bell)
        self.s.tm("select-window", "-t", "A:1")
        selected = self.s.eval(a, "#{E:window-status-current-format}")
        self.assertIn("bg=#8bd5ca,bold] 1:", selected)
        self.assertNotIn("#30464b", selected)
        applied = self.s.option("window-status-format")
        self.s.load()
        self.assertEqual(applied, self.s.option("window-status-format"))
        self.s.load("none")
        self.assertEqual(theme, self.s.option("window-status-format"))
        self.assertEqual(current, self.s.option("window-status-current-format"))

    def test_compact_icon_keeps_plain_tab_padding(self):
        self.s.tm("set-option", "-g", "window-status-format", " #I #W ")
        a = self.s.agent()
        self.s.load("compact")
        self.s.busy(a)
        value = self.s.eval(a, "#{E:window-status-format}")
        self.assertRegex(value, r" 1 \S+ ⚙ #\[default\]")
        self.s.load("none")
        self.assertNotIn("@agent-status-internal-preset", self.s.option("window-status-format"))
        self.assertRegex(self.s.eval(a, "[#{E:window-status-format}]"), r"^\[ 1 \S+ \]$")

    def _padded_tab(self, theme):
        # The accent must extend past the icon, so the tab cannot end at it.
        self.s.tm("set-option", "-g", "window-status-format", theme)
        a = self.s.agent()
        self.s.load("compact")
        self.s.busy(a)
        busy = re.sub(r"#\[[^]]*\]", "", self.s.eval(a, "[#{E:window-status-format}]"))
        self.s.busy(a, on=False)
        idle = re.sub(r"#\[[^]]*\]", "", self.s.eval(a, "[#{E:window-status-format}]"))
        self.s.load("none")
        self.assertEqual(theme, self.s.option("window-status-format"))
        return busy, idle

    def test_compact_icon_is_padded_in_tmux_default_format(self):
        # tmux's default ends in a flags-or-space conditional, not a literal space.
        busy, idle = self._padded_tab("#I:#W#{?window_flags,#{window_flags}, }")
        self.assertRegex(busy, r"^\[ 1:\S+? ⚙ \]$")
        self.assertRegex(idle, r"^\[1:\S+?( |[^ ])\]$")
        self.assertNotIn("  ", busy + idle)

    def test_compact_icon_is_padded_in_tabs_without_padding(self):
        busy, idle = self._padded_tab("#[bg=blue]#I #W")
        self.assertRegex(busy, r"^\[ 1 \S+ ⚙ \]$")
        self.assertRegex(idle, r"^\[1 \S+\]$")

    def test_compact_preset_with_popular_themes(self):
        for name, (inactive, current, options) in THEMES.items():
            with self.subTest(theme=name):
                self.check_theme(inactive, current, options)

    def check_theme(self, inactive, current, options):
        s = Server()
        self.addCleanup(s.close)
        for key, value in options.items():
            s.tm("set-option", "-g", key, value)
        s.tm("set-option", "-g", "window-status-format", inactive)
        s.tm("set-option", "-g", "window-status-current-format", current)
        a = s.agent()
        s.tm("set-option", "-w", "-t", a, "automatic-rename", "off")
        s.tm("rename-window", "-t", a, "agent")
        # Brackets keep tm() from stripping the format's own padding.
        cells = lambda option: render_cells(s.eval(a, f"[#{{E:{option}}}]"))[1:-1]
        for option, accent in (("window-status-format", RUNNING_BG),
                               ("window-status-current-format", None)):
            if accent is None:
                s.tm("select-window", "-t", a)
            s.load("none")
            original = cells(option)
            s.load("compact")
            # Idle tabs look exactly as they did without the preset.
            self.assertEqual(original, cells(option), f"idle {option}")
            s.busy(a)
            busy = cells(option)
            s.busy(a, False)
            text = "".join(ch for ch, _ in busy)
            self.assertEqual(1, text.count("⚙"), f"{option}: {text!r}")
            i = text.index("⚙")
            # The icon sits in the tab body, with padding after it in the same color.
            self.assertGreater(i, 1, f"{option}: {text!r}")
            self.assertEqual(" ", text[i - 1], f"{option}: {text!r}")
            self.assertLess(i + 1, len(text), f"{option} ends at the icon: {text!r}")
            self.assertEqual(busy[i - 1][1], busy[i][1], f"{option}: {busy!r}")
            self.assertEqual(busy[i][1], busy[i + 1][1], f"{option}: {busy!r}")
            # An inactive busy tab takes the accent, including at the icon.
            if accent:
                self.assertEqual(accent, busy[i][1], f"{option}: {busy!r}")
                index = text.index("1")
                self.assertEqual(accent, busy[index][1], f"{option}: {busy!r}")
                self.assertGreater(index, 0, f"{option} starts at the label: {text!r}")
                self.assertEqual(accent, busy[index - 1][1], f"{option}: {busy!r}")
        s.load("none")
        self.assertEqual(inactive, s.raw_option("window-status-format"))
        self.assertEqual(current, s.raw_option("window-status-current-format"))

    def test_compact_icon_goes_before_a_trailing_style_conditional(self):
        theme = "#[bg=#363a4f] #W#{?window_bell_flag,#[bg=red] BELL,}"
        self.s.tm("set-option", "-g", "window-status-format", theme)
        self.s.load("compact")
        self.assertIn("#W#{E:@agent-status-internal-preset-window-icon}"
                      "#{E:@agent-status-internal-preset-window-pad}#{?window_bell_flag,",
                      self.s.option("window-status-format"))
        self.s.load("none")
        self.assertEqual(theme, self.s.option("window-status-format"))

    def test_compact_icon_falls_back_to_the_end(self):
        # Without a window label there is no tab content to place the icon after.
        theme = "#[bg=#363a4f] #T"
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

    def test_icon_sets_and_overrides(self):
        a = self.s.agent()
        self.s.load()
        self.s.busy(a)
        self.assertEqual("⚙", self.s.eval(a, PUBLIC))
        self.s.emit(a, "\a")
        self.assertEqual(BELL, self.s.eval(a, PUBLIC))
        self.s.tm("set-option", "-g", "@agent-status-icons", "emoji")
        self.s.load()
        self.assertEqual("🔔", self.s.eval(a, PUBLIC))
        self.s.tm("set-option", "-g", "@agent-status-bell-icon", "!")
        self.s.load()
        self.assertEqual("!", self.s.eval(a, PUBLIC))
        self.s.tm("set-option", "-g", "@agent-status-icons", "nerdfont")
        before = self.s.tm("show-options", "-g")
        result = self.s.load(check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("@agent-status-icons", result.stderr)
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

    def test_compact_widens_status_right_for_the_corner(self):
        self.s.tm("set-option", "-g", "status-right", "x" * 39)
        self.s.tm("set-option", "-g", "status-right-length", "40")
        length = lambda: self.s.tm("show-options", "-gv", "status-right-length")
        self.s.load("compact")
        self.assertEqual("49", length())
        # Reloading the plugin does not widen it again.
        self.s.load()
        self.assertEqual("49", length())
        # A config reload that resets status-right but not its length.
        self.s.tm("set-option", "-g", "status-right", "x" * 39)
        self.s.load()
        self.assertEqual("49", length())
        # A config that sets its own length starts from that.
        self.s.tm("set-option", "-g", "status-right-length", "60")
        self.s.load()
        self.assertEqual("69", length())
        self.s.load("none")
        self.assertEqual("60", length())
        self.s.load("compact")
        self.s.tm("run-shell", shlex.quote(str(ROOT / "agent-status.tmux")) + " --uninstall")
        self.assertEqual("60", length())
        # The bell indicator fits after a full status-right.
        self.s.tm("set-option", "-g", "status-right-length", "40")
        self.s.load("compact")
        a = self.s.agent()
        c = self.s.attach("B:0")
        self.s.emit(a, "\a")
        clipped = self.s.eval("B:0", "#{T;=/#{status-right-length}:status-right}", c)
        self.assertIn(BELL, clipped)

    def test_compact_takes_only_stock_tree_keys(self):
        keys = lambda k: self.s.tm("list-keys", "-T", "prefix", k)
        self.s.tm("bind-key", "-T", "prefix", "w", "choose-tree", "-Zw", "-O", "name")
        self.s.load("compact")
        self.assertIn("@agent-status-internal-tree-format", keys("s"))
        self.assertIn("-O name", keys("w"))
        a = self.s.agent()
        self.s.emit(a, "\a")
        tree = "#{E:@agent-status-internal-tree-format}"
        sessions = dict(line.split(" ", 1) for line in self.s.tm(
            "list-sessions", "-F", f"#{{session_name}} {tree}").splitlines())
        self.assertTrue(sessions["A"].endswith(BELL), sessions)
        self.assertNotIn(BELL, sessions["B"])
        self.s.load("none")
        self.assertTrue(keys("s").endswith("choose-tree -Zs"), keys("s"))
        self.assertIn("-O name", keys("w"))

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
