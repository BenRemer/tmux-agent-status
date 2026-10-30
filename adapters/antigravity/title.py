#!/usr/bin/env python3
"""Translate Antigravity's title payload into tmux-agent-status activity."""
import json
import sys


def title(payload):
    state = payload.get("agent_state") if isinstance(payload, dict) else None
    return "⠋ agy" if state in ("working", "tool_use") else "agy"


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        payload = None
    print(title(payload))


if __name__ == "__main__":
    main()
