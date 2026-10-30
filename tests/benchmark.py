#!/usr/bin/env python3
"""Measure the native formats, optionally comparing an older inline baseline."""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import time

from integration import Server

parser = argparse.ArgumentParser()
parser.add_argument("--baseline", type=Path,
                    help="optional older config containing inline @agent-* definitions")
parser.add_argument("--samples", type=int, default=30)
parser.add_argument("--counts", type=int, nargs="+", default=[1, 10, 40])
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


def cpu_ticks(pid):
    path = Path(f"/proc/{pid}/stat")
    if not path.exists():
        return None
    raw = path.read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return int(fields[11]) + int(fields[12])


results = []
for count in args.counts:
    server = Server()
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
            formats = [("plugin", "#{E:@agent-status-other}")]
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
                ticks_before = cpu_ticks(pid)
                start = time.monotonic()
                updates = 0
                while time.monotonic() - start < 2:
                    glyph = "⠋" if updates % 2 else "⠙"
                    for descriptor in descriptors:
                        os.write(descriptor, f"\x1b]2;{glyph} Working\x07".encode())
                    updates += len(descriptors)
                    time.sleep(.1)
                elapsed = time.monotonic() - start
                ticks_after = cpu_ticks(pid)
                written_after = int(server.eval("B:0", "#{client_written}", client))
                record = {
                    "agent_panes": count,
                    "total_panes": count + 2,
                    "implementation": name,
                    "median_command_ms": round(statistics.median(latencies), 3),
                    "p95_command_ms": round(sorted(latencies)[math.ceil(len(latencies) * .95) - 1], 3),
                    "title_updates": updates,
                    "terminal_bytes": written_after - written_before,
                    "cpu_percent_one_core": None if ticks_before is None else round(
                        (ticks_after - ticks_before) / os.sysconf("SC_CLK_TCK") / elapsed * 100, 2),
                }
                results.append(record)
                print(json.dumps(record), flush=True)
        finally:
            for descriptor in descriptors:
                os.close(descriptor)
    finally:
        server.close()
