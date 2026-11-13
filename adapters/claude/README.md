# Claude activity adapter

Recent Claude Code versions keep their terminal title static inside tmux, so
title matching cannot detect active work. This optional Claude mod reports
main-turn start, completion (including cancellation), and session exit to a
pane-local tmux option. Subagents count as work too, so the cog stays on while
a workflow's agents keep running after the main turn ends; their completion
never clears the main turn's marker and never rings. A background shell command
is the one gap: Claude reports no event for it, so a tab whose only remaining
work is a background command shows no cog until the follow-up turn starts.
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

Use `terminal_bell` if you approve tool permissions by hand: with `auto`, a
tab waiting on a permission prompt or an MCP input request keeps its cog and
never rings. If Claude rarely asks you anything (for example in auto mode),
`auto` is enough and gives exactly one bell per finished turn.

With `terminal_bell`, Claude also rings its idle reminder ("Claude is waiting
for your input") about 60 seconds after a turn ends, so one turn can ring
twice. Claude sends that reminder itself, outside the mods API, and hooks
cannot cancel it, so the adapter cannot suppress it. To skip it, set
`"messageIdleNotifThresholdMs": 86400000` (24 hours) at the top level of
`~/.claude.json`, Claude's global config file, and restart Claude.

When a background command or agent finishes after Claude's turn has ended,
Claude starts a follow-up turn on its own. That turn notifies only if it ends
at least `@agent-status-followup-bell-seconds` (default 30) after the previous
turn, so a quick background command doesn't notify twice; long background work
still notifies when it's done. Set it to `0` to notify for every follow-up.
Turns that start from a prompt you type always notify.

The fallback bell rings in the window you are viewing only after a turn of at
least `@agent-status-viewed-bell-seconds` (default 10), the same rule as the
plugin's completion bell. A completion
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
