# Antigravity activity title

Antigravity does not update the terminal title until a title command is
configured. Recognizing the `agy` command alone therefore produces neither a
running cog nor a completion bell. This adapter provides both: the plugin's
[completion bell](../../README.md#completion-bell) rings when the busy title
turns idle, so agy's own `"notifications"` setting is not needed for tmux.

This optional adapter reads Antigravity's JSON title payload and prints a
busy title for `working` and `tool_use`. All other states, including `idle`,
`reviewing`, and `error`, produce an idle title. It reads no transcripts,
starts no tmux commands, and does not emit or change notifications.

Requires Python 3 and an Antigravity version with custom title support.

## Install

Merge this into `~/.gemini/antigravity-cli/settings.json` on the machine
**running agy**:

```json
{
  "title": {
    "type": "command",
    "command": "python3 \"$HOME/.tmux/plugins/tmux-agent-status/adapters/antigravity/title.py\"",
    "enabled": true
  }
}
```

If you already have a custom `title.command`, keep a copy before replacing it.
This adapter uses the terminal title for activity; it does not combine an
existing title script with its own output. Adjust the path if the tmux plugin
is installed elsewhere, and ensure `python3` is available to agy.

Restart/resume agy. With the plugin's default recognition patterns, the title
`⠋ agy` produces a cog while work is active, and `agy` clears it when idle.
When the title returns to `agy`, the plugin rings the tab's bell. If you also
enable agy's own notifications, you may get two bells per turn. Turn one off,
for example with `set -g @agent-status-completion-bell off`. An unread bell
takes precedence over the cog on a tab.

To remove the adapter, restore your previous title configuration or remove
the `title` block, then restart agy.

## Validate without an agent

```sh
printf '%s\n' '{"agent_state":"working"}' | python3 adapters/antigravity/title.py
printf '%s\n' '{"agent_state":"idle"}' | python3 adapters/antigravity/title.py
```

Expected output is `⠋ agy` and `agy`, respectively. This checks translation
only; it does not substitute for a live agy task.

Reference: Antigravity's official
[title configuration](https://antigravity.google/docs/cli/title/) and
[payload schema](https://antigravity.google/docs/cli/statusline/).
