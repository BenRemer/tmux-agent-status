import { expect, mock, test } from 'claude-code/testing'

function setup(on, env = { TMUX: '/tmp/socket with spaces,and commas,321,0', TMUX_PANE: '%42' }) {
  const writes = []
  const notifications = []
  mock.env(on, env)
  mock.clock(on)
  on('process.run', ($, e) => {
    writes.push(e.argv)
    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  on('ui.notify', ($, e) => {
    notifications.push(e.text)
    return { value: { isSent: true, channel: 'terminal_bell' } }
  })
  on('session.start', () => ({ cwd: '/tmp' }))
  on('session.end', ($, e) => ({ sessionId: e.sessionId }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  return { writes, notifications }
}

const terminal = { surface: 'terminal', isInteractive: true, cwd: '/tmp' }

test('main turn reports busy, child completion does not clear it, cancellation does', async ($, on) => {
  const { writes, notifications } = setup(on)
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'main' })
  await $.turn.start({ turnId: 'child', agentId: 'child' })
  await $.turn.complete({ turnId: 'child', agentId: 'child', isAborted: false, answer: 'Done', durationMs: 1 })
  expect(writes.length).toBe(2)
  expect(writes[1]).toEqual([
    'tmux', '-S', '/tmp/socket with spaces,and commas',
    'set-option', '-p', '-F', '-t', '%42', '@agent-status-busy-command', '#{pane_current_command}',
  ])
  await $.turn.complete({ turnId: 'main', isAborted: true, answer: '', durationMs: 1 })
  expect(writes[2][writes[2].length - 1]).toBe('')
  expect(notifications.length).toBe(0)
})

test('a subagent that outlives the main turn keeps the pane busy', async ($, on) => {
  const { writes, notifications } = setup(on)
  const busy = (write) => write[write.length - 1]
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'main' })
  await $.turn.start({ turnId: 'child', agentId: 'child' })
  // The Workflow tool returns at once, so the main turn ends first. It still
  // rings, but the pane stays busy while the workflow's agents run.
  await $.turn.complete({ turnId: 'main', isAborted: false, answer: 'Done', durationMs: 1 })
  expect(writes.length).toBe(2)
  expect(busy(writes[1])).toBe('#{pane_current_command}')
  expect(notifications).toEqual(['Task complete'])
  await $.turn.complete({ turnId: 'child', agentId: 'child', isAborted: false, answer: 'Done', durationMs: 1 })
  expect(busy(writes[2])).toBe('')
  // A finished subagent never rings by itself.
  expect(notifications).toEqual(['Task complete'])
})

test('the last of several subagents clears the pane, and an abort still clears', async ($, on) => {
  const { writes, notifications } = setup(on)
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'main' })
  await $.turn.start({ turnId: 'a', agentId: 'a' })
  await $.turn.start({ turnId: 'b', agentId: 'b' })
  await $.turn.complete({ turnId: 'main', isAborted: false, answer: 'Done', durationMs: 1 })
  await $.turn.complete({ turnId: 'a', agentId: 'a', isAborted: false, answer: 'Done', durationMs: 1 })
  expect(writes.length).toBe(2)
  await $.turn.complete({ turnId: 'b', agentId: 'b', isAborted: true, answer: '', durationMs: 1 })
  expect(writes[2][writes[2].length - 1]).toBe('')
  expect(notifications).toEqual(['Task complete'])
})

test('a subagent alone reports busy, and session exit clears it', async ($, on) => {
  const { writes, notifications } = setup(on)
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'child', agentId: 'child' })
  expect(writes[1][writes[1].length - 1]).toBe('#{pane_current_command}')
  expect(notifications.length).toBe(0)
  await $.session.end({ sessionId: 'session', reason: 'prompt_input_exit' })
  expect(writes[2][writes[2].length - 1]).toBe('')
})

test('a subagent running through a follow-up turn does not change its bell', async ($, on) => {
  const { notifications, clock } = followUpSetup(on)
  await $.session.start(terminal)
  await turn($, 'first')
  await $.turn.start({ turnId: 'child', agentId: 'child' })
  await clock.advance(29000)
  await turn($, 'follow-up', 'task-notification')
  expect(notifications).toEqual(['Task complete'])
  await $.turn.complete({ turnId: 'child', agentId: 'child', isAborted: false, answer: 'Done', durationMs: 1 })
  await settle()
  expect(notifications).toEqual(['Task complete'])
})

test('old completion cannot clear a newer active turn; normal completion and exit clear', async ($, on) => {
  const { writes, notifications } = setup(on)
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'old' })
  await $.turn.start({ turnId: 'new' })
  await $.turn.complete({ turnId: 'old', isAborted: false, answer: 'Done', durationMs: 1 })
  expect(writes.length).toBe(2)
  expect(notifications.length).toBe(0)
  await $.turn.complete({ turnId: 'new', isAborted: false, answer: 'Done', durationMs: 1 })
  expect(writes[2][writes[2].length - 1]).toBe('')
  await $.turn.start({ turnId: 'last' })
  await $.session.end({ sessionId: 'session', reason: 'prompt_input_exit' })
  expect(writes[4][writes[4].length - 1]).toBe('')
  expect(notifications).toEqual(['Task complete'])
})

test('no tmux connection means no process is started', async ($, on) => {
  const { writes, notifications } = setup(on, {})
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'main' })
  await $.turn.complete({ turnId: 'main', isAborted: false, answer: 'Done', durationMs: 1 })
  expect(writes.length).toBe(0)
  expect(notifications.length).toBe(0)
})

test('noninteractive runs cannot overwrite the parent terminal state', async ($, on) => {
  const { writes, notifications } = setup(on)
  await $.session.start({ ...terminal, isInteractive: false })
  await $.turn.start({ turnId: 'headless' })
  await $.turn.complete({ turnId: 'headless', isAborted: false, answer: 'Done', durationMs: 1 })
  expect(writes.length).toBe(0)
  expect(notifications.length).toBe(0)
})

test('an unavailable tmux server does not interrupt event handling', async ($, on) => {
  mock.env(on, { TMUX: '/tmp/gone,321,0', TMUX_PANE: '%42' })
  mock.clock(on)
  let completions = 0
  on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: 'no server' } }))
  on('session.start', () => ({ cwd: '/tmp' }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => { completions += 1; return { text: '' } })
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'main' })
  await $.turn.complete({ turnId: 'main', isAborted: true, answer: '', durationMs: 1 })
  expect(completions).toBe(1)
})

test('main completion notifies once even when the event is repeated', async ($, on) => {
  const { notifications } = setup(on)
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'main' })
  const finished = { turnId: 'main', isAborted: false, answer: 'Done', durationMs: 1 }
  await $.turn.complete(finished)
  await $.turn.complete(finished)
  expect(notifications).toEqual(['Task complete'])
})

test('a refused notification does not prevent turn completion', async ($, on) => {
  mock.env(on, { TMUX: '/tmp/socket,321,0', TMUX_PANE: '%42' })
  mock.clock(on)
  let completions = 0
  on('process.run', () => ({ value: { exitCode: 0, stdout: '', stderr: '' } }))
  on('ui.notify', () => ({ deny: 'notifications disabled for this test' }))
  on('session.start', () => ({ cwd: '/tmp' }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => { completions += 1; return { text: '' } })
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'main' })
  await $.turn.complete({ turnId: 'main', isAborted: false, answer: 'Done', durationMs: 1 })
  expect(completions).toBe(1)
})

function bellSetup(on, notifyResult, viewed = false, seconds = '10') {
  const commands = []
  mock.env(on, { TMUX: '/tmp/socket,321,0', TMUX_PANE: '%42' })
  mock.clock(on)
  on('process.run', ($, e) => {
    commands.push(e.argv)
    const stdout = e.argv.includes('display-message') ? `${viewed ? 1 : 0} ${seconds} /dev/ttys004\n` : ''
    return { value: { exitCode: 0, stdout, stderr: '' } }
  })
  on('ui.notify', () => ({ value: notifyResult }))
  on('session.start', () => ({ cwd: '/tmp' }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  return commands
}

async function completeOneTurn($, durationMs = 1) {
  await $.session.start(terminal)
  await $.turn.start({ turnId: 'main' })
  await $.turn.complete({ turnId: 'main', isAborted: false, answer: 'Done', durationMs })
  // The notification runs after completion returns; let it finish.
  for (let i = 0; i < 20; i += 1) await Promise.resolve()
}

const bellWrite = ['sh', '-c', 'printf "\\a" > "$1"', 'sh', '/dev/ttys004']

test('without a bell channel, completion rings the pane bell itself', async ($, on) => {
  const commands = bellSetup(on, { isSent: false, reason: 'no-channel' })
  await completeOneTurn($)
  expect(commands.slice(3)).toEqual([
    ['tmux', '-S', '/tmp/socket', 'display-message', '-p', '-t', '%42',
      '#{&&:#{window_active},#{session_attached}} #{@agent-status-internal-viewed-bell-seconds} #{pane_tty}'],
    bellWrite,
  ])
})

test('a desktop-notification channel still gets a tmux bell', async ($, on) => {
  const commands = bellSetup(on, { isSent: true, channel: 'kitty' })
  await completeOneTurn($)
  expect(commands[commands.length - 1]).toEqual(bellWrite)
})

test('the window being viewed gets no fallback bell for a short turn', async ($, on) => {
  const commands = bellSetup(on, { isSent: false, reason: 'no-channel' }, true)
  await completeOneTurn($, 9999)
  expect(commands.length).toBe(4)
  expect(commands[3][3]).toBe('display-message')
})

test('the window being viewed rings after a long turn, for an outer tmux', async ($, on) => {
  const commands = bellSetup(on, { isSent: false, reason: 'no-channel' }, true)
  await completeOneTurn($, 10000)
  expect(commands[commands.length - 1]).toEqual(bellWrite)
})

test('the viewed-window threshold comes from the plugin, with a default', async ($, on) => {
  const commands = bellSetup(on, { isSent: false, reason: 'no-channel' }, true, '2')
  await completeOneTurn($, 2000)
  expect(commands[commands.length - 1]).toEqual(bellWrite)
})

test('without the plugin loaded, the viewed-window threshold defaults to 10 seconds', async ($, on) => {
  const commands = bellSetup(on, { isSent: false, reason: 'no-channel' }, true, '')
  await completeOneTurn($, 9999)
  expect(commands.length).toBe(4)
})

test('a terminal_bell channel is not rung twice', async ($, on) => {
  const commands = bellSetup(on, { isSent: true, channel: 'terminal_bell' })
  await completeOneTurn($)
  expect(commands.length).toBe(3)
})

test('notifications_disabled is respected', async ($, on) => {
  const commands = bellSetup(on, { isSent: false, reason: 'disabled' })
  await completeOneTurn($)
  expect(commands.length).toBe(3)
})

function followUpSetup(on, seconds = '') {
  const commands = []
  const notifications = []
  mock.env(on, { TMUX: '/tmp/socket,321,0', TMUX_PANE: '%42' })
  const clock = mock.clock(on)
  on('process.run', ($, e) => {
    commands.push(e.argv)
    const format = e.argv[e.argv.length - 1]
    const stdout = format === '#{@agent-status-internal-followup-bell-seconds}' ? `${seconds}\n` : ''
    return { value: { exitCode: 0, stdout, stderr: '' } }
  })
  on('ui.notify', ($, e) => {
    notifications.push(e.text)
    return { value: { isSent: true, channel: 'terminal_bell' } }
  })
  on('session.start', () => ({ cwd: '/tmp' }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  return { commands, notifications, clock }
}

async function settle() {
  for (let i = 0; i < 20; i += 1) await Promise.resolve()
}

async function turn($, turnId, kind) {
  if (kind) await $.prompt.submit({ text: 'notice', origin: { kind }, wait: false })
  await $.turn.start({ turnId })
  await $.turn.complete({ turnId, isAborted: false, answer: 'Done', durationMs: 1 })
  await settle()
}

test('a follow-up turn soon after the previous one does not ring again', async ($, on) => {
  const { notifications, clock } = followUpSetup(on)
  await $.session.start(terminal)
  await turn($, 'first')
  await clock.advance(29000)
  await turn($, 'follow-up', 'task-notification')
  expect(notifications).toEqual(['Task complete'])
})

test('a follow-up turn after the quiet period rings', async ($, on) => {
  const { notifications, clock } = followUpSetup(on)
  await $.session.start(terminal)
  await turn($, 'first')
  await clock.advance(30000)
  await turn($, 'follow-up', 'task-notification')
  expect(notifications).toEqual(['Task complete', 'Task complete'])
})

test('a prompt the user types always rings, however soon', async ($, on) => {
  const { notifications } = followUpSetup(on)
  await $.session.start(terminal)
  await turn($, 'first')
  await turn($, 'second', 'composer')
  expect(notifications).toEqual(['Task complete', 'Task complete'])
})

test('the quiet period comes from the plugin option, and 0 always rings', async ($, on) => {
  const { notifications } = followUpSetup(on, '0')
  await $.session.start(terminal)
  await turn($, 'first')
  await turn($, 'follow-up', 'task-notification')
  expect(notifications).toEqual(['Task complete', 'Task complete'])
})
