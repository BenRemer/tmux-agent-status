# Nested tmux and SSH

Load the plugin in both servers. For the outer tmux to show the inner
server's agents on its SSH tab, turn on the relay in the **inner** server:

```tmux
set -g @agent-status-relay on
```

See [Remote tmux over SSH](../README.md#remote-tmux-over-ssh) for what the
outer tab shows and the options that go with it.

For terminal bells to reach the outer layer, configure each relevant layer:

```tmux
set -g monitor-bell on
set -g bell-action any
set -g visual-bell both
```

`visual-bell on` displays a message but does not forward the audible bell;
`both` requests the message and forwarding. The terminal controls whether the
final bell produces sound or an OS notification.

Live forwarding requires an attached client. An agent in a detached session
can leave a native bell flag, which the plugin shows in another session's
corner, but this is not independent OS-notification delivery.

If you set `pane-title-changed` hooks of your own, give them an index, such
as `set-hook -g 'pane-title-changed[0]' …`. A hook set without an index
replaces every `pane-title-changed` hook, including the plugin's completion
bell. Avoid setting pane options on every title change, too: tmux redraws the
whole pane each time, and the relay title changes every second.
