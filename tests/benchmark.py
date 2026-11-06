#!/usr/bin/env python3
"""Measure the native formats, optionally comparing an older inline baseline."""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import time

from integration import Server

parser = argparse.ArgumentParser()
parser.add_argument("--baseline", type=Path,
                    help="optional older config containing inline @agent-* definitions")
parser.add_argument("--samples", type=int, default=30)
parser.add_argument("--counts", type=int, nargs="+", default=[1, 10, 40])
parser.add_argument("--relay", action="store_true",
                    help="also publish the relay title, as a remote tmux does")
args = parser.parse_args()
if args.samples < 1 or any(count < 1 for count in args.counts):
    parser.error("samples and pane counts must be positive")
definitions = ""
if args.baseline:
    definitions = "\n".join(
        line for line in args.baseline.read_text().splitlines()
        if line.startswith("set -g @agent-")
    )
    if "@agent-other-status" not in definitions:
        parser.error("baseline must contain the original inline @agent-* definitions")


def cpu_seconds(pid):
    """CPU time used so far by a process: /proc on Linux, ps elsewhere."""
    path = Path(f"/proc/{pid}/stat")
    if path.exists():
        raw = path.read_text()
        fields = raw[raw.rfind(")") + 2:].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
    try:
        out = subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True,
                             text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    # [[dd-]hh:]mm:ss.ss
    days, _, clock = out.rpartition("-")
    seconds = 0.0
    for part in clock.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds + (int(days) * 86400 if days else 0)


results = []
for count, bell in [(count, bell) for count in args.counts for bell in ("off", "on")]:
    server = Server()
    server.tm("set-option", "-g", "@agent-status-completion-bell", bell)
    if args.relay:
        server.tm("set-option", "-g", "@agent-status-relay", "on")
    try:
        panes = [server.agent(f"A:{n + 1}") for n in range(count)]
        client = server.attach("B:0")
        for pane in panes:
            server.busy(pane)
        if definitions:
            baseline = Path(server.temp.name) / "baseline.conf"
            baseline.write_text(definitions + "\n")
            server.tm("source-file", str(baseline))
        server.load()
        pid = server.eval("B:0", "#{pid}")
        descriptors = [
            os.open(server.eval(pane, "#{pane_tty}"), os.O_WRONLY | os.O_NOCTTY)
            for pane in panes
        ]
        try:
            name = "plugin" if bell == "off" else "plugin+bell"
            formats = [(name + ("+relay" if args.relay else ""), "#{E:@agent-status-other}")]
            if definitions:
                formats.insert(0, ("inline", "#{E:@agent-other-status}"))
            for name, fmt in formats:
                server.tm("set-option", "-g", "status-right", fmt)
                latencies = []
                for _ in range(args.samples):
                    start = time.monotonic()
                    assert "⚙" in server.eval("B:0", fmt, client)
                    latencies.append((time.monotonic() - start) * 1000)
                written_before = int(server.eval("B:0", "#{client_written}", client))
                cpu_before = cpu_seconds(pid)
                start = time.monotonic()
                updates = 0
                while time.monotonic() - start < 2:
                    glyph = "⠋" if updates % 2 else "⠙"
                    for descriptor in descriptors:
                        os.write(descriptor, f"\x1b]2;{glyph} Working\x07".encode())
                    updates += len(descriptors)
                    time.sleep(.1)
                elapsed = time.monotonic() - start
                cpu_after = cpu_seconds(pid)
                written_after = int(server.eval("B:0", "#{client_written}", client))
                record = {
                    "agent_panes": count,
                    "total_panes": count + 2,
                    "implementation": name,
                    "median_command_ms": round(statistics.median(latencies), 3),
                    "p95_command_ms": round(sorted(latencies)[math.ceil(len(latencies) * .95) - 1], 3),
                    "title_updates": updates,
                    "terminal_bytes": written_after - written_before,
                    "cpu_percent_one_core": None if cpu_before is None else round(
                        (cpu_after - cpu_before) / elapsed * 100, 2),
                }
                results.append(record)
                print(json.dumps(record), flush=True)
        finally:
            for descriptor in descriptors:
                os.close(descriptor)
    finally:
        server.close()
