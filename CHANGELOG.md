# Changelog

## Unreleased

- The completion bell, and the Claude adapter's fallback bell, ring for the
  window you are viewing only after a turn of at least 10 seconds. tmux passes
  those bells straight to the terminal, so starting Codex flashed the screen
  with a visual bell; skipping the viewed window entirely meant an outer tmux
  showing another tab never heard about a finished Codex turn.
- The compact preset adds session and window indicators to the prefix + s
  and prefix + w trees while those keys are tmux's stock `choose-tree`
  bindings. Customized bindings are left alone; preset `none` and
  `--uninstall` restore the stock ones.
- The compact preset raises `status-right-length` by the corner's width when
  it appends the corner, so a full `status-right` no longer clips the corner
  to a bare colored space. Preset `none` and `--uninstall` give the width back.
- Remote tmux over SSH: set `@agent-status-relay on` on the remote, and the
  local SSH tab shows the whole remote tmux like a local agent tab: the cog
  while any remote agent is busy, the bell while any remote window has an
  unread bell (including bells in sessions the remote client isn't viewing),
  and both in the corner from other sessions. Claude panes count through
  their adapter. A
  relay older than 30 seconds shows the new stale icon (a broken link,
  `@agent-status-stale-icon`), styled with `@agent-status-stale-style`.
  `@agent-status-relay-count on` adds busy/total counts (`⚙ 2/3`).
  `--uninstall` restores the remote's own title settings.
- `agent-status.tmux --uninstall` removes everything the plugin set: preset
  tokens, the completion-bell hook, and its options. Before this, removing
  the plugin left the completion bell ringing until tmux restarted.
- The compact preset handles more themes, now covered by fixture tests built
  from catppuccin, dracula, nord, gruvbox, onedark, tmux-power and themepack:
  - catppuccin's palette references (`bg=#{@thm_blue}`) take the accent;
  - a second content block counts as part of the tab;
  - reversed separator caps keep their colors;
  - the icon stays inside the tab when a style conditional, such as
    gruvbox's, follows the label.
- Slimmer repository: the validation record, contributing guide, issue and
  PR templates, and release-packaging workflow are gone. Development commands
  are in the README and known limitations in Troubleshooting.
- New completion bell: when a recognized agent's busy title turns idle, the
  plugin rings that tab's bell. Codex now needs no setup. Antigravity needs
  only the title adapter, not its notification setting. It runs only tmux
  commands per title change, plus one shell command per finished turn.
  Disable it with `@agent-status-completion-bell off`.
- The compact preset pads both ends of the accent when a tab has no
  space of its own before the label or after the icon, including tmux's
  default window format. The colored tab no longer starts at the first
  character or ends at the icon. Formats that begin with a
  style now get the icon inside the tab instead of at the end.
- The Claude adapter now rings the tmux bell on turn completion even when
  Claude's notification channel is the default `auto`, which sends nothing
  inside tmux. It also rings for OSC desktop-notification channels. It still
  respects `notifications_disabled` and does not ring twice with
  `terminal_bell`. The README explains what each `preferredNotifChannel` value
  does and why `terminal_bell` is still recommended.
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
- The integration tests run on macOS, and the macOS CI job builds tmux with
  utf8proc as its configure script requires.
- The compact preset places the icon before a plain tab's trailing padding,
  so the tab no longer ends right at the icon.
- The default bell icon is now the Nerd Font bell (U+F0F3, `nf-fa-bell`), sized like the cog.
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
- Agent versions can change title and notification behavior.
- Notifications use native tmux window flags. They are not a per-pane inbox and
  do not survive a tmux server restart.
- Claude's active turn includes time waiting for tool permission.
