# Claude activity adapter

Recent Claude Code versions keep their terminal title static inside tmux, so
title matching cannot detect active work. This optional Claude mod reports
main-turn start, completion (including cancellation), and session exit to a
pane-local tmux option. Subagent events do not clear the main turn's marker.
Normal main-turn completion rings the tmux bell. The adapter uses Claude's
notification channel, or rings the bell itself when that channel cannot reach
tmux. See [Bells](#bells-and-preferrednotifchannel). Cancellation and subagent
completion do not ring.

Requires Claude Code with mods support (2.1.314 or later).

With tmux-agent-status installed at its usual path, load this adapter for one
Claude session:

```sh
claude --plugin-dir "$HOME/.tmux/plugins/tmux-agent-status/adapters/claude"
```

To load it automatically for new Claude sessions, create a user-plugin symlink:

```sh
mkdir -p "$HOME/.claude/skills"
ln -s "$HOME/.tmux/plugins/tmux-agent-status/adapters/claude" \
  "$HOME/.claude/skills/tmux-agent-status"
```

Do not overwrite an existing directory with that name. Restart/resume Claude
after installing. Claude may show its normal local-plugin trust prompt.
Remove the symlink and restart Claude to uninstall this adapter.

## Bells and `preferredNotifChannel`

tmux shows a bell marker only when the pane writes a BEL character. On main
turn completion, the adapter first asks Claude to notify through its
configured channel. Then it acts on the result:

| `preferredNotifChannel` | What happens on completion |
|---|---|
| `terminal_bell`, `iterm2_with_bell` | Claude writes BEL. The adapter does nothing more. |
| `auto` (default) | Inside tmux, `auto` finds no channel, so Claude sends nothing. The adapter writes BEL to the pane's tty, which it reads from `tmux display -p '#{pane_tty}'`. |
| `iterm2`, `kitty`, `ghostty` | Claude sends its OSC desktop notification. That sets no tmux bell flag, so the adapter also writes BEL. |
| `notifications_disabled` | Nothing. The adapter respects it. |

The fallback covers turn completion only. Claude's own notifications, such as
permission prompts and idle input, reach tmux only through a BEL-writing
channel. To get those too, run `/config` in Claude and set **Notifications**
to **Terminal Bell**, or add this top-level key to `~/.claude/settings.json`
alongside your other settings (wrap it in `{ }` if the file is new):

```json
"preferredNotifChannel": "terminal_bell"
```

The fallback bell rings in the window you are viewing only after a turn of at
least 10 seconds, the same rule as the plugin's completion bell. A completion
bell creates an unread marker only if the notified window is not currently
being viewed. The marker also appears in other sessions' corner
indicators.

The adapter runs one `tmux` command per activity change, plus two (read the
pane's tty, write BEL) when it rings a fallback bell. It uses `TMUX` and
`TMUX_PANE` to select the correct server and pane. It does nothing outside
interactive tmux sessions. It does not change titles, permissions, or
conversation content, and never starts a model request. A running turn
includes time waiting for tool permission.

The pane-local `@agent-status-busy-command` option holds the pane's
foreground command (normally `claude`, or a launcher's name such as
`toolbox-exec`) while a main turn is active, and is empty when idle. The tmux plugin accepts it only while
that command is in the foreground and recognized as an agent. If Claude is
killed without cleanup, its marker is ignored once the shell returns; the
next Claude session clears the old marker on startup.

## Validation

```sh
claude plugin validate --strict /path/to/tmux-agent-status/adapters/claude
claude plugin test /path/to/tmux-agent-status/adapters/claude
```

The tests use Claude's local event harness; they make no model requests. If a
launcher prepends flags and `plugin test` rejects that spelling, use the
installed Claude executable directly.

This adapter is part of tmux-agent-status and is distributed under the
[MIT license](../../LICENSE). It is optional; installing the tmux plugin
does not automatically modify your Claude configuration.

Reference: Claude Code's official mods event documentation describes
`turn.start`, `turn.complete` (including `isAborted`), and session events:
`https://code.claude.com/docs/en/plugins/mods/events`
`https://code.claude.com/docs/en/plugins/mods/reference`
