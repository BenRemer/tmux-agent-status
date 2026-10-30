# Changelog

## 0.1.0-beta.2

- Recognize Antigravity's `agy` command by default, alongside Codex and Claude.
  Activity still requires a matching busy title or an activity-reporting integration.

## 0.1.0-beta.1

First public beta package, prepared October 30, 2026.

- Native running and bell indicators for windows, sessions, and other sessions.
- Manual format tokens and an optional compact preset with soft running accents.
- Configurable icons, styles, and command/title recognition patterns.
- Cross-session bell aggregation that includes every window, including the
  selected window of an inactive session.
- Preset reload and removal that preserve unrelated status-bar content.
- Optional Claude Code adapter for activity, cancellation, and completion
  notifications, tested with public Claude Code 2.1.314.
- MIT license, illustrated setup documentation, isolated tests, and release
  archives with SHA-256 checksums.

### Beta limitations

- macOS tests are configured in CI but have not yet run on the hosted repository.
- Agent versions can change title and notification behavior; see
  [validation.md](validation.md) for the exact evidence.
- Notifications use native tmux window flags. They are not a per-pane inbox and
  do not survive a tmux server restart.
- Claude's active turn includes time waiting for tool permission.
