// The main turn owns the pane. Subagent completion must not clear its activity.
const activeTurns = new Set();
let connection;
let reported;

async function reportActivity($, busy) {
  try {
    if (connection === undefined) {
      const tmux = await $.env.get('TMUX');
      const pane = await $.env.get('TMUX_PANE');
      const match = typeof tmux === 'string' && tmux.match(/^(.*),[0-9]+,[0-9]+$/);
      connection = match && match[1] && typeof pane === 'string' && /^%[0-9]+$/.test(pane)
        ? { socket: match[1], pane }
        : null;
    }
    if (!connection || reported === busy) return;
    // Record the pane's own foreground command, since a launcher such as
    // toolbox-exec can run Claude under another name.
    const result = await $.process.run([
      'tmux', '-S', connection.socket,
      'set-option', '-p', '-F', '-t', connection.pane,
      '@agent-status-busy-command', busy ? '#{pane_current_command}' : '',
    ]);
    if (result.exitCode === 0) reported = busy;
  } catch {
    // A missing tmux server must never stop a Claude turn or its completion.
  }
}

// Claude's channels that write BEL, which tmux turns into a window bell.
const BELL_CHANNELS = new Set(['terminal_bell', 'iterm2_with_bell']);

async function notifyCompletion($, target, elapsedMs) {
  let result;
  try {
    result = await $.ui.notify('Task complete');
  } catch {
    // A hook or the channel refused the notification; respect that.
    return;
  }
  // Respect an explicit `notifications_disabled`, and do nothing without a
  // terminal. Otherwise make sure tmux sees a bell: Claude's default `auto`
  // channel finds no method inside tmux, and OSC desktop notifications
  // (iterm2, kitty, ghostty) do not set tmux's bell flag.
  if (!result || BELL_CHANNELS.has(result.channel)) return;
  if (!result.isSent && result.reason !== 'no-channel') return;
  await ringPaneBell($, target, elapsedMs);
}

const DEFAULT_VIEWED_BELL_SECONDS = 10;

async function ringPaneBell($, target, elapsedMs) {
  try {
    // The pane's tty, and whether someone is viewing its window. There tmux
    // sets no unread marker, so like the plugin's completion bell, only a turn
    // long enough to matter rings: tmux passes that bell on to an outer tmux,
    // which may be showing another tab.
    const info = await $.process.run([
      'tmux', '-S', target.socket,
      'display-message', '-p', '-t', target.pane,
      '#{&&:#{window_active},#{session_attached}} #{@agent-status-internal-viewed-bell-seconds} #{pane_tty}',
    ]);
    const [viewed, seconds = '', path = ''] =
      info.exitCode === 0 ? info.stdout.trim().split(' ') : [];
    const minimum = /^[0-9]+$/.test(seconds) ? Number(seconds) : DEFAULT_VIEWED_BELL_SECONDS;
    if (viewed !== '0' && !(viewed === '1' && elapsedMs >= minimum * 1000)) return;
    if (!/^\/dev\/[A-Za-z0-9/._-]+$/.test(path)) return;
    // Writing BEL to the pane's terminal is what an application ringing the
    // bell does; tmux sets the window's bell flag from it.
    await $.process.run(['sh', '-c', 'printf "\\a" > "$1"', 'sh', path]);
  } catch {
    // A missing tmux server must never stop a Claude turn or its completion.
  }
}

export function register(on) {
  on('session.start', async ($, e, next) => {
    activeTurns.clear();
    reported = undefined;
    connection = e.surface === 'terminal' && e.isInteractive ? undefined : null;
    await reportActivity($, false);
    return next(e);
  });

  on('turn.start', async ($, e, next) => {
    if (!e.agentId) {
      activeTurns.add(e.turnId);
      await reportActivity($, true);
    }
    return next(e);
  });

  on('turn.complete', async ($, e, next) => {
    if (!e.agentId) {
      const wasActive = activeTurns.delete(e.turnId);
      await reportActivity($, activeTurns.size > 0);
      if (connection && wasActive && activeTurns.size === 0 && !e.isAborted) {
        // Never delay completion for a notification, and never notify for
        // cancellation or child turns.
        notifyCompletion($, connection, e.durationMs).catch(() => {});
      }
    }
    return next(e);
  });

  on('session.end', async ($, e, next) => {
    activeTurns.clear();
    await reportActivity($, false);
    return next(e);
  });
}
