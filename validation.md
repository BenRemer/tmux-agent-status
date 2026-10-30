# Validation record

Beta `0.1.0-beta.2`, verified locally on Linux on October 30, 2026. Unreleased
changes were also verified locally on macOS the same day.
Pending checks are listed explicitly.

## Development update after beta.2

The `dev` branch adds an Antigravity title adapter. All 14 integration tests
passed on the same four Linux tmux builds below, including translation of
working, tool-use, idle, review, error, and unknown states, invalid input,
other-session cogs, and independent completion bells. These are synthetic
payload tests; the adapter still needs a live Antigravity check on the
affected machine. The user confirmed that Antigravity's bells already work.
The packaged beta.2 results below predate this adapter.

## Compatibility

| Runtime | Evidence |
|---|---|
| tmux 3.4, upstream release | All 13 integration tests passed |
| tmux 3.5a, upstream release | All 13 integration tests passed |
| tmux 3.6a, upstream release | All 13 integration tests passed |
| tmux next-3.7, local development build | All 13 integration tests passed |
| tmux 1.8 | Rejected before changing options |
| macOS 26.7.2, Homebrew tmux 3.7b (unreleased changes) | All 17 integration tests (including the Antigravity adapter test) and all 7 Claude adapter event tests passed locally; running and bell markers checked on a live server with Claude under `toolbox-exec`. Hosted CI run pending |
| Codex | Live desktop use with build 0.166.0.827; README settings checked against the public 0.166.0 configuration schema |
| Claude Code 2.1.314, public distribution | Strict adapter validation and all 7 event tests passed with a fresh configuration directory |
| Antigravity (`agy`) | Command recognition and busy/idle titles covered by synthetic integration tests; live CLI not tested |
| Claude in live desktop use | User confirmed both activity and completion notifications work |

The public Claude runtime was installed separately for testing. Validation and
event tests require no API credentials and make no model requests. Live
desktop confirmation is separate evidence; it is not a new automated model run.

Agent versions may change their titles, events, or notification behavior.
This table records tested versions rather than promising compatibility with
every past or future release.

## Integration coverage

The tests create isolated tmux servers and attached, drained PTYs. Harmless
copies of `cat` named `codex` and `claude` exercise actual foreground-command
recognition without invoking agents.

Covered behavior includes:

- Busy, idle, hidden, zoomed, and dead panes.
- Claude's static-title activity marker and stale state after the command exits.
- Bells on the selected window of an inactive session, including subsequent
  completion output and configuration reloads.
- Multiple unread bells, multiple clients, linked windows, session renaming,
  and moving windows.
- Current-window styling and native bell acknowledgment.
- Idempotent preset reloads, removal, later theme edits, and existing manual
  tokens.
- Compact accents and icon placement in a powerline theme with inline colors,
  and the fallback for a closing style inside a conditional.
- Activity reported for an agent running under a launcher's command name.
- Empty overrides, invalid regular expressions, and shell metacharacters in
  configuration values.
- Corner padding and restoration of adjacent text colors, measured from
  actual terminal output.

Test socket paths contain spaces and a comma. The Claude event tests cover
normal completion, cancellation, subagent isolation, overlapping turns,
session exit, absent tmux, noninteractive sessions, duplicate completion, and
notification refusal.

## Release checks

- ShellCheck passes for the entry point and preset helper.
- Actionlint passes for the test and draft-release workflows.
- Release metadata, executable permissions, and local documentation links pass.
- The source archive was extracted into a fresh directory containing spaces
  and an apostrophe. All 13 integration tests, strict Claude adapter validation,
  and all 7 adapter event tests passed from that extraction. The entry point
  retained its executable bit; the license, version, documentation, and all
  three images were present.
- README images were generated from an isolated tmux server and visually
  reviewed. Captions and sample content are synthetic; the status output
  comes from the plugin. See [image provenance](docs/images/README.md).
- The public hosted installation and macOS jobs await repository creation.
- The checks above ran against beta 2 on Linux; they have not been repeated
  for the unreleased changes.

## Performance

`tests/benchmark.py` measures local format-command latency and tmux server CPU
while updating titles at 10 Hz per agent. Each setup includes the listed
agent panes plus two idle panes and an attached observer in another session.
The default run takes 30 latency samples per setup.

Local results with tmux next-3.7:

| Agent panes | Median command | p95 command | CPU, one core |
|---|---|---|---|
| 1 | 2.796 ms | 3.178 ms | 0.0% |
| 10 | 3.396 ms | 3.890 ms | 0.5% |
| 40 | 5.507 ms | 6.256 ms | 1.0% |

The two-second title-update samples emitted 0, 0, and 287 terminal bytes,
respectively, consistent with occasional status redraws.

The core installs no recurring process or shell commands in status formats.
Shell work happens only at plugin load or reload. The optional Claude adapter
runs a tmux command when activity changes.

These measurements include client process/socket overhead. Short CPU samples
have coarse resolution. This is a bounded local benchmark, not a measurement
of end-to-end SSH latency or a diagnosis of terminal lag.

```sh
python3 tests/benchmark.py
```

To compare against an existing inline configuration containing the original
`@agent-*` definitions:

```sh
python3 tests/benchmark.py --baseline /path/to/inline-tmux.conf
```

## Beta limitations

- Native bells belong to windows, not individual panes. Viewing the window
  acknowledges its bell; another client can acknowledge a shared window too.
- Bell history does not survive a tmux server restart.
- Other-session indicators cover one tmux server. Nested or remote servers
  need a separate relay if their outer status bar should reflect inner state.
- Custom `status-format` layouts require manual token placement.
- Claude's active turn includes time waiting for tool permission.
- Hosted macOS CI and a fresh install from the public GitHub repository remain
  pending. macOS has been verified on one local machine only.
- The compact preset tints inline tab colors only when they are literal colors
  set before the window index or name.
