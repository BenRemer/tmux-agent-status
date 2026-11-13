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

A launcher can leave its own name in the foreground; for example, Claude
installed through Amazon's Toolbox reports `toolbox-exec`. Claude's `✳` title
still identifies the pane, and the adapter reports whichever command is in
the foreground. For other launchers, add the launcher name to
`@agent-status-command-pattern` or rely on a title pattern.

For Claude's static title, install the [Claude adapter](../adapters/claude/README.md)
and restart/resume Claude. In recent Claude versions, `/plugins` lists loaded
plugins. The adapter should appear as `tmux-agent-status@skills-dir` when
installed through the README's symlink. A version without mods support cannot
run it.

The adapter reports main-turn activity. Waiting for a tool permission is still
part of that active turn. It is not a CPU-usage indicator.

For Antigravity, configure the [title adapter](../adapters/antigravity/README.md)
on the machine running `agy`. A working bell does not imply that activity is
being reported. For a tab with an unread bell, the bell takes priority over
the running cog.

## “Activity in window” covers the status bar

This is tmux's visual **activity** alert, triggered by terminal output. It is
separate from the plugin's running cog and terminal-bell indicators. A theme
such as tmux-power can style the message and have its status sections covered
by it without being the component that enabled the alert.

On the affected tmux server, suppress that popup immediately:

```sh
tmux set-option -g visual-activity off
tmux set-option visual-activity off
```

The second command also handles an override on the current session. For a
persistent setting, put `set -g visual-activity off` after your theme and plugin
initialization in `.tmux.conf`. Remove any conflicting session-specific setting.
This leaves `monitor-bell`, `bell-action`, and the plugin's bell icons unchanged.
Apply it to the layer displaying the message if you use nested tmux.

If you also do not want ordinary terminal output to trigger activity alerts,
set `activity-action none` on that server. Keep `monitor-bell on` for actual
completion bells.

## tmux-power overwrites the cog or corner

Load tmux-power before tmux-agent-status. The theme replaces window and status
formats when loaded, so loading it afterward removes the plugin's placement.
With TPM, order the entries like this before TPM initializes:

```tmux
set -g @plugin 'wfxr/tmux-power'
set -g @plugin 'benremer/tmux-agent-status#dev'
set -g @agent-status-preset 'compact'
```

The `#dev` suffix selects the currently published development branch. When
using manual mode, place the public tokens in your final formats after the
theme loads. Adding `@agent-status-preset 'compact'` changes placement, but
does not make an agent publish activity.

## The bell icon is a box or question mark

The default bell is a Nerd Font glyph. If the terminal showing tmux does not
use a Nerd Font, set this before the plugin loads, then reload:

```tmux
set -g @agent-status-icons 'emoji'
```

Over SSH, the font that matters is the one on the machine running the
terminal, not the remote host.

## The cog works but there is no bell

Activity and notification delivery are separate. First test the native path:

```sh
sleep 3; printf '\a'
```

Switch to another window before it rings. If its tab gets a bell, the tmux
path works and the agent needs notification setup.

- Codex and agy: the plugin's completion bell rings when the busy title
  turns idle. Check that `@agent-status-completion-bell` is not `off`, and
  that the cog appears while the agent works. No cog means no busy title,
  and then there is nothing to detect. For agy, install the title adapter.
- Claude: install the [adapter](../adapters/claude/README.md); without it,
  Claude's default `auto` channel sends nothing inside tmux. Check that
  `preferredNotifChannel` is not `notifications_disabled`. Set it to
  `terminal_bell` so permission prompts and other Claude notifications ring
  too, not just turn completion.
- Check `monitor-bell on` and `bell-action any` in the relevant tmux server.

Changes to agent configuration may require restarting/resuming that agent.
A bell in the window you are already viewing may show a transient message
without leaving an unread flag. Visit a different window before testing.

## Claude rings twice for one turn

With `preferredNotifChannel` set to `terminal_bell`, the second bell about a
minute after the turn ends is Claude's idle reminder, not the adapter. Raise
`messageIdleNotifThresholdMs` in `~/.claude.json`; see the
[adapter README](../adapters/claude/README.md#bells-and-preferrednotifchannel).
A second bell soon after a background command finishes is a follow-up turn;
see `@agent-status-followup-bell-seconds`.

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
compact preset loaded successfully. When the compact preset adds the corner
to `status-right`, it raises `status-right-length` by the corner's width, and
gives that width back with preset `none` or `--uninstall`. If you placed
`#{E:@agent-status-other}` yourself, increase `status-right-length` if other
status content leaves too little room.

If the theme replaced your formats after the plugin loaded, load the plugin
after the theme. Use manual tokens for a custom `status-format`.

## The whole status line blinks or briefly goes blank

tmux 3.8 stops expanding a format that runs past its time limit, and draws
what it has so far, often nothing. Time your status line:
`time tmux display -p '#{E:status-format[0]}'` should take a few milliseconds
plus the cost of starting tmux. If it takes much longer, remove status
content one piece at a time to find the slow part.

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

When reporting an issue, include your OS, terminal, `tmux -V`, the agent's
version, and the diagnostics above. Leave out transcripts and full configs.

## An SSH tab shows no cog, or the stale icon

On the remote, check that `@agent-status-relay` is `on` and reloaded, and
that its `status-interval` is between 1 and 15. On the local tmux, inside the
SSH pane's window:

```sh
tmux display-message -p '#{pane_current_command} | #{pane_title}'
```

The title should look like `agents 1/3 !0 ~1793903991`: busy and total
agents, unread bells, and the time. The command should
match `@agent-status-relay-command-pattern` (`ssh`, `mosh-client`, or `et` by
default). A wrapper such as `autossh` needs adding to that pattern. If the
number after `~` stops advancing, the remote is no longer redrawing its
status line. That usually means a hung connection, which is what the stale
icon reports.

## Known limitations

- Bells belong to windows, not panes. Viewing a window acknowledges its bell,
  and another client viewing the same window can acknowledge it too.
- Bells do not survive a tmux server restart.
- Other-session indicators cover one tmux server. A remote tmux reports into
  the local one only with the [relay](../README.md#remote-tmux-over-ssh)
  turned on, and only while one of its clients is attached through the SSH
  pane.
- Custom `status-format` layouts need manual token placement.
- The compact preset tints a theme's inline tab colors only when they are
  literal colors set before the window index or name.
- Claude's running turn includes time spent waiting for tool permission.
