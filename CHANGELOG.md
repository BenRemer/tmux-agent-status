# Changelog

## Unreleased

- Add an optional Antigravity title adapter to translate its working state
  into the running cog without changing completion bells.
- Document tmux activity popups and load order with tmux-power.
- Run the existing CI checks on pushes to the public development branch.
- The compact preset now works with themes that draw tabs with inline colors,
  such as powerline layouts: the tab body and its separators take the running
  or bell accent, and the icon is placed inside the tab before its closing
  separator. Layouts it cannot read keep the previous behavior.
- The Claude adapter reports the pane's actual foreground command, so activity
  works when Claude runs under a launcher such as `toolbox-exec`.
- The integration tests run on macOS.
- The default bell icon is now the Nerd Font bell ``, sized like the cog.
  Set `@agent-status-icons 'emoji'` to keep 🔔 in terminals without a Nerd
  Font.

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
