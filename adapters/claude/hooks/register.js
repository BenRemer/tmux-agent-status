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
        // Use Claude's notification channel; never delay completion for a
        // notification hook, and never notify for cancellation or child turns.
        $.ui.notify('Task complete').catch(() => {});
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
