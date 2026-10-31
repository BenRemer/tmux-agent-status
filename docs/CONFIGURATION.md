# Configuration

Set input options before the plugin loads. Reload the plugin after changing
them. The plugin resolves defaults without overwriting your input options.

## Placement and styling

`@agent-status-preset` is `none` by default. Set it to `compact` for automatic
placement. The compact preset decorates the existing global
`window-status-format`, `window-status-current-format`, and `status-right`.
It does not replace the whole theme or change key bindings.

Themes that draw tabs with inline colors, such as powerline layouts, would
hide a wrapping accent. For these, the preset reads the literal `bg=`/`fg=`
colors in effect before the window index or name and routes every use of
those colors in the tab format, including separators, through the running or
bell accent. It places the icon before the tab's closing style and separator.
If the colors are not literal, or the closing style is inside a conditional,
it falls back to wrapping the tab and appending the icon.

| Input | Manual default | Compact default |
|---|---|---|
| `@agent-status-icons` | `nerd-font` | `nerd-font` |
| `@agent-status-running-icon` | `⚙` | `⚙` |
| `@agent-status-bell-icon` | `` | `` |

The default bell is the Nerd Font bell `` (U+F0F3), which is text-sized
like the cog. `@agent-status-icons 'emoji'` uses 🔔 instead, for terminals
without a Nerd Font; emoji usually render two cells wide. Explicit icon inputs
override either set. tmux cannot query the terminal's font, so the plugin
cannot detect which set will display.
| `@agent-status-running-style` | Inherit | `bg=#30464b,fg=#cad3f5` |
| `@agent-status-bell-style` | Inherit | `bg=#eed49f,fg=#181926,bold` |

Style inputs affect the corner indicators and compact preset accents.
Window and session text tokens inherit the surrounding style. To add manual
tab accents, see [the dark-theme example](../examples/dark-theme.conf).

An explicitly empty style means inherit the current theme, even in compact
mode:

```tmux
set -g @agent-status-running-style ''
```

The preset recognizes existing public window and corner tokens and does not
add a second copy. Reloading removes only its own decoration tokens before
reapplying them, so unrelated changes made by a theme or another plugin stay.
If a theme replaces the formats later, reload this plugin after that theme.

Custom `status-format` layouts and window-local format overrides need manual
placement. The preset warns when it cannot identify a standard layout.
It also preserves damaged or edited private tokens and asks you to remove
them explicitly rather than guessing which content is safe to delete.

## Public formats

Expand these with `#{E:...}`:

| Option | Output |
|---|---|
| `@agent-status-window` | Bell, otherwise running, otherwise empty |
| `@agent-status-session` | Running and/or bell for this session |
| `@agent-status-other` | Running and/or bell for other sessions |

Window and session text include leading spacing. Corner badges have padding
on both sides. All three are empty when idle with no notification.

Numeric formats expand to `0` or `1`:

```text
@agent-status-window-busy
@agent-status-window-bell
@agent-status-session-busy
@agent-status-session-bell
@agent-status-other-busy
@agent-status-other-bell
```

For example:

```tmux
set -g window-status-style 'bg=#{?#{E:@agent-status-window-busy},#30464b,default}'
```

Other-session state is relative to the viewing tmux client. Session checks
visit every window, including the selected window of an inactive session.
Busy detection visits every live pane, including panes hidden by zoom.

Options prefixed `@agent-status-internal-` are implementation details and may
change between beta versions.

## Recognition patterns

Patterns are extended regular expressions:

```tmux
set -g @agent-status-command-pattern '^(codex|claude|agy)$'
set -g @agent-status-agent-title-pattern '^✳ '
set -g @agent-status-busy-title-pattern '^(⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏) '
```

A pane is recognized as an agent if its foreground command **or** title
matches the corresponding pattern. A recognized pane is working if its title
matches the busy pattern or an adapter reports activity. A static `✳` title
alone does not signal work. Dead panes are ignored.

Empty patterns disable that recognition path. Patterns, icons, and styles
must be single-line values. Invalid regular expressions are rejected before
the plugin changes its configuration.

Adding a command name does not make its activity detectable automatically.
Inspect that agent's actual title changes or use an adapter.

## Reporting activity from another agent

An optional integration can set the **pane-local** option
`@agent-status-busy-command` to the agent's foreground command name while it
is working:

```sh
tmux set-option -p -t "$TMUX_PANE" @agent-status-busy-command my-agent
```

Clear it on completion, cancellation, and exit:

```sh
tmux set-option -p -t "$TMUX_PANE" @agent-status-busy-command ''
```

Also clear it on a fresh agent startup. Never set it globally. For an
integration running outside a tmux client process, use the correct socket
with `tmux -S` rather than relying on the default server.

The command must pass the configured recognition rule and match
`pane_current_command`. That prevents a leftover marker from labelling a
different foreground program as busy after an agent exits.

This option reports activity only. Emit a terminal BEL from the agent's
terminal or its supported notification API for a notification. Do not use
`tmux send-keys` to inject a bell into the application's input.

## Refresh, messages, and nested terminals

The plugin does not change `status-interval`. Indicators appear on the next
tmux status refresh. An interval of five seconds is a reasonable starting
point; it is not a background polling process added by this plugin.

`monitor-bell on` and `bell-action any` enable the native bell behavior used
by the examples. Transient messages are separate from persistent tab flags:

```tmux
set -g visual-bell on
set -g display-time 1500
```

`display-time` controls tmux messages in milliseconds, not the lifetime of
unread bell icons. These settings affect other tmux messages too.

For nested tmux and SSH, see [the nested setup](../examples/nested-tmux.md).
Sound, dock indicators, desktop notifications, and full-window visual effects
are controlled by the terminal app.
