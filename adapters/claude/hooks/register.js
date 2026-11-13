// The main turn owns the pane: only its completion rings, and a subagent's
// completion must never clear its activity. Subagents still count as work,
// because the Workflow and Agent tools keep running after the main turn ends;
// without that the cog went out while a workflow was still going.
const activeTurns = new Set();
const childTurns = new Set();
let connection;
let reported;
let activityUpdate = Promise.resolve();
// A finished background task's notification starts a follow-up turn of its
// own once Claude is idle. That turn rings again only when it ends long enough
// after the previous turn, so a quick background command does not ring twice.
let followUpPending = false;
const followUpTurns = new Set();
let lastCompletedAt;
const DEFAULT_FOLLOWUP_BELL_SECONDS = 30;

const isBusy = () => activeTurns.size > 0 || childTurns.size > 0;

function reportActivity($) {
  // Child events can overlap while a tmux command is pending. Serialize the
  // writes and read the current turn state when each queued update starts.
  activityUpdate = activityUpdate.then(() => writeActivity($));
  return activityUpdate;
}

async function writeActivity($) {
  try {
    if (connection === undefined) {
      const tmux = await $.env.get('TMUX');
      const pane = await $.env.get('TMUX_PANE');
      const match = typeof tmux === 'string' && tmux.match(/^(.*),[0-9]+,[0-9]+$/);
      connection = match && match[1] && typeof pane === 'string' && /^%[0-9]+$/.test(pane)
        ? { socket: match[1], pane }
        : null;
    }
    const busy = isBusy();
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

// The follow-up quiet period, from the plugin's option (0 always rings).
async function followUpSeconds($, target) {
  try {
    const info = await $.process.run([
      'tmux', '-S', target.socket,
      'display-message', '-p', '-t', target.pane,
      '#{@agent-status-internal-followup-bell-seconds}',
    ]);
    const value = info.exitCode === 0 ? info.stdout.trim() : '';
    return /^[0-9]+$/.test(value) ? Number(value) : DEFAULT_FOLLOWUP_BELL_SECONDS;
  } catch {
    return DEFAULT_FOLLOWUP_BELL_SECONDS;
  }
}

async function notifyCompletion($, target, elapsedMs, sincePreviousMs) {
  if (sincePreviousMs !== undefined &&
      sincePreviousMs < (await followUpSeconds($, target)) * 1000) return;
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
    childTurns.clear();
    followUpTurns.clear();
    followUpPending = false;
    lastCompletedAt = undefined;
    reported = undefined;
    connection = e.surface === 'terminal' && e.isInteractive ? undefined : null;
    await reportActivity($);
    return next(e);
  });

  on('prompt.submit', async ($, e, next) => {
    // Only a submission while idle starts a turn; one delivered into a running
    // turn (turnId set) joins it.
    if (!e.turnId) followUpPending = e.origin?.kind === 'task-notification';
    return next(e);
  });

  on('turn.start', async ($, e, next) => {
    if (e.agentId) {
      // A subagent, including a background workflow's agents: work to show,
      // but never a turn that rings.
      childTurns.add(e.turnId);
    } else {
      if (followUpPending) followUpTurns.add(e.turnId);
      followUpPending = false;
      activeTurns.add(e.turnId);
    }
    await reportActivity($);
    return next(e);
  });

  on('turn.complete', async ($, e, next) => {
    if (e.agentId) {
      // A subagent's own completion only stops showing its work.
      if (childTurns.delete(e.turnId)) await reportActivity($);
    } else {
      const wasActive = activeTurns.delete(e.turnId);
      const followUp = followUpTurns.delete(e.turnId);
      await reportActivity($);
      if (wasActive && activeTurns.size === 0) {
        const now = await $.clock.now();
        const since = followUp && lastCompletedAt !== undefined ? now - lastCompletedAt : undefined;
        lastCompletedAt = now;
        if (connection && !e.isAborted) {
          // Never delay completion for a notification, and never notify for
          // cancellation or child turns.
          notifyCompletion($, connection, e.durationMs, since).catch(() => {});
        }
      }
    }
    return next(e);
  });

  on('session.end', async ($, e, next) => {
    activeTurns.clear();
    childTurns.clear();
    followUpTurns.clear();
    await reportActivity($);
    return next(e);
  });
}
