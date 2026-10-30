# Troubleshooting

## There is no running icon

Inside the affected pane:

```sh
tmux display-message -p '#{pane_current_command} | #{pane_title}'
tmux display-message -p '#{E:@agent-status-window-busy}'
```

Check that the command or title matches the configured recognition pattern,
and that the title exposes a working state. An idle agent should not show a
running icon. Wrappers and executable paths containing spaces can change the
command name reported by tmux.

For Claude's static title, install the [Claude adapter](../adapters/claude/README.md)
and restart/resume Claude. In recent Claude versions, `/plugins` lists loaded
plugins. The adapter should appear as `tmux-agent-status@skills-dir` when
installed through the README's symlink. A version without mods support cannot
run it.

The adapter reports main-turn activity. Waiting for a tool permission is still
part of that active turn. It is not a CPU-usage indicator.

## The cog works but there is no bell

Activity and notification delivery are separate. First test the native path:

```sh
sleep 3; printf '\a'
```

Switch to another window before it rings. If its tab gets a bell, the tmux
path works and the agent needs notification setup.

- Codex: enable notifications, choose `notification_method = "bel"`, and set
  `notification_condition = "always"`.
- Claude: use the adapter and set `"preferredNotifChannel": "terminal_bell"`
  in its settings. An automatic OS-notification channel may not emit BEL.
- Check `monitor-bell on` and `bell-action any` in the relevant tmux server.

Changes to agent configuration may require restarting/resuming that agent.
A bell in the window you are already viewing may show a transient message
without leaving an unread flag. Visit a different window before testing.

## A bell seems to disappear

The plugin uses native tmux window flags. Viewing that window acknowledges
its bell, including through another client or a linked window. Extra agent
output does not acknowledge it.

The corner tracks **other sessions**. Switching into the notified session
moves attention to its tab indicators. If several windows have unread bells,
visiting one leaves the others intact.

This plugin does not preserve unread notifications across tmux server restarts.

## The corner is missing or clipped

Verify that `status-right` contains `#{E:@agent-status-other}` or that the
compact preset loaded successfully. Increase `status-right-length` if other
status content leaves too little room. The plugin leaves your width choices
unchanged.

If the theme replaced your formats after the plugin loaded, load the plugin
after the theme. Use manual tokens for a custom `status-format`.

## There is a large yellow message or a border around the whole terminal

These effects are separate from the plugin's small tab and corner icons:

| Effect | Controlled by |
|---|---|
| Temporary tmux message | `visual-bell`, `message-style`, `display-time` |
| Persistent highlighted tab | Plugin preset, or your manual tab styles |
| Full-window border, sound, or dock attention | Your terminal app |

For example, Ghostty's `bell-features = no-border` disables its bell border.
If you already configure `bell-features`, add `no-border` to that list.
This does not disable tmux's tab and corner indicators.

## Nested tmux or SSH behaves differently

Both layers have their own bell flags. A visual message in the inner layer
does not guarantee the bell was forwarded to the outer layer. See
[nested-tmux.md](../examples/nested-tmux.md) for `visual-bell both` and a
step-by-step test.

Remote jobs keep running when SSH disconnects, but the plugin cannot deliver
a real-time desktop notification through a disconnected terminal.

## An error is hidden by the plugin manager

Load the plugin explicitly from inside tmux:

```sh
tmux run-shell '~/.tmux/plugins/tmux-agent-status/agent-status.tmux'
```

The plugin reports unsupported tmux versions, invalid recognition patterns,
unknown presets, and unsupported automatic-placement layouts.

If reporting an issue, include only the relevant settings and sanitized
diagnostics. See [CONTRIBUTING.md](../CONTRIBUTING.md).
