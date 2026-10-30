# Claude activity adapter

Recent Claude Code versions keep their terminal title static inside tmux, so
title matching cannot detect active work. This optional Claude mod reports
main-turn start, completion (including cancellation), and session exit to a
pane-local tmux option. Subagent events do not clear the main turn's marker.
Normal main-turn completion also requests a notification through Claude's
configured notification channel. Cancellation and subagent completion do not.

Requires Claude Code with mods support. Validated with public Claude Code
2.1.314, with activity and completion also confirmed in live desktop use.
Older clients that cannot load hook modules need an upgrade.

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

For tmux bell markers, merge this setting into `~/.claude/settings.json`:

```json
{
  "preferredNotifChannel": "terminal_bell"
}
```

Claude's `auto` channel may select a desktop-notification protocol or find no
available channel; neither produces the BEL event needed by tmux. The adapter
respects this preference, including `notifications_disabled`. A completion
bell creates an unread marker only if the notified window is not currently
being viewed. The marker also appears in other sessions' corner indicators.

The adapter runs one `tmux` command per activity change, using `TMUX` and
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
