import { expect, mock, test } from 'claude-code/testing'

function setup(on, env = { TMUX: '/tmp/socket with spaces,and commas,321,0', TMUX_PANE: '%42' }) {
  const writes = []
  const notifications = []
  mock.env(on, env)
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
