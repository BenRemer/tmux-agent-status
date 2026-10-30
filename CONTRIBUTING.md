# Contributing

Bug reports, documentation improvements, and small pull requests are welcome.

## Report a problem

Include your OS, terminal, `tmux -V`, agent version, installation method, and
whether you use the compact preset or manual formats. Say what you expected,
what happened, and whether the same issue occurs with a plain terminal bell.
Avoid attaching transcripts, credentials, private hostnames, or entire configs.

For detection problems, these commands are useful **inside the affected pane**:

```sh
tmux display-message -p '#{pane_current_command} | #{pane_title}'
tmux display-message -p 'busy=#{E:@agent-status-window-busy} bell=#{window_bell_flag}'
```

Review their output for private information before sharing it.

## Develop

The runtime uses POSIX shell and native tmux formats. Python 3 is needed for
the integration suite, and ShellCheck for shell linting:

```sh
shellcheck -x -s sh agent-status.tmux scripts/preset.sh
python3 tests/integration.py
python3 tools/check_release.py
```

Tests start disposable tmux servers with temporary sockets and harmless
executables named `codex` and `claude`. They do not attach to your server, load
your dotfiles, or make model requests. To test another tmux build:

```sh
TMUX_BIN=/path/to/tmux python3 tests/integration.py
```

The optional Claude adapter uses Claude Code's own local test harness:

```sh
claude plugin validate --strict adapters/claude
claude plugin test adapters/claude
```

CI pins a public Claude Code version for these checks. If your launcher adds
arguments that `plugin test` rejects, invoke the underlying Claude executable.
No API credentials are needed for validation or these tests.

## Keep the runtime small

- Keep status rendering in tmux formats. Do not add polling, log scraping,
  model requests, or shell commands to each status refresh.
- Preserve existing themes, key bindings, and unrelated status content.
- Keep agent integrations optional. Report only activity, not conversation text.
- Test behavior changes with an isolated server or the adapter's event harness.
- Keep the README, examples, and supported-version record in sync.

See [the image instructions](docs/images/README.md) to regenerate the demos and
[the release checklist](docs/RELEASING.md) to package a version.

Contributions are distributed under this repository's [MIT license](LICENSE).
