# Nested tmux and SSH

The plugin can be loaded independently in either server. Its entry point uses
the invoking server's socket. Do not assume the outer server can see process
names or pane titles inside the inner server.

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

This plugin aggregates activity within one tmux server. If you already use a
custom title relay to display inner-server activity on an outer server, keep
that relay separate; installing this plugin does not create one.

No macOS runtime validation has been performed from the Linux development
host. The integration suite and CI workflow are prepared for a Mac runner.
