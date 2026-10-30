# tmux-agent-status 0.1.0-beta.1

See which agent tabs are working and which have a notification, without
replacing your tmux theme.

- Compact running and bell icons on tabs.
- Soft running accents and notification highlights.
- A corner indicator for activity and unread bells in other sessions.
- Automatic placement with the compact preset, or manual format tokens.
- Configurable icons, styles, and agent-recognition patterns.
- Optional Claude Code adapter for activity and completion notifications.
- No status-time shell polling, transcript scraping, or model requests.

Requires tmux 3.4+. Use the README's agent setup instructions in addition to
installing the tmux plugin.

This is a beta. Linux tests and real desktop usage are recorded in
`validation.md`; macOS is covered by the release workflow but remains pending
until that workflow has actually run. Claude's adapter is tested with public
Claude Code 2.1.314. Other releases may differ. Bell notifications are native
tmux window flags, so visiting a notified window acknowledges them.

Both the source archive and its SHA-256 checksum are attached. Licensed under MIT.
