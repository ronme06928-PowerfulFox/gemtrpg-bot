import assert from 'node:assert/strict';
globalThis.window = {};
const { IntentPerformance, intentPerformance } = await import('../../static/js/battle/core/IntentPerformance.js');

let now = 0;
let visible = true;
let sequence = 0;
const frames = new Map();
const timers = new Map();
const recorder = new IntentPerformance({
  now: () => now,
  visible: () => visible,
  frame: (callback) => { const key = ++sequence; frames.set(key, callback); return key; },
  cancelFrame: (key) => frames.delete(key),
  setTimer: (callback) => { const key = ++sequence; timers.set(key, callback); return key; },
  clearTimer: (key) => timers.delete(key),
  makeId: () => `synthetic-request-${++sequence}`,
});
const sent = [];
const socket = { connected: true, io: { engine: { transport: { name: 'websocket' } } }, emit: (...args) => sent.push(args) };
const payload = { room_id: 'private-room', skill_id: 'private-skill' };
function send() {
  recorder.emit(socket, 'battle_intent_commit', payload);
  return sent.at(-1);
}
function ack(row, emitted = true) {
  row[2]({ intent_perf: { id: row[1]._intent_perf_id, handler_ms: 5, stages_ms: { redirect_ms: 2 }, state_emitted: emitted } });
}
function receive(row) {
  recorder.receive({ _intent_perf: { id: row[1]._intent_perf_id } }, () => {
    recorder.render(() => { now += 3; });
    now += 2;
  });
}
function frame() {
  const current = [...frames];
  frames.clear();
  for (const [, callback] of current) callback();
}
const scenario = process.argv[2];
if (scenario === 'wiring') {
  const { socketClient } = await import('../../static/js/battle/core/SocketClient.js');
  const { store } = await import('../../static/js/battle/core/BattleStore.js');
  const { declarePanel } = await import('../../static/js/battle/components/DeclarePanel.js');
  const handlers = new Map();
  socket.on = (name, callback) => handlers.set(name, callback);
  window.socket = socket;
  socketClient.initialize();
  Object.assign(intentPerformance, {
    now: () => now, visible: () => false,
    setTimer: recorder.setTimer, clearTimer: recorder.clearTimer, makeId: recorder.makeId,
  });
  let renders = 0;
  declarePanel._render = () => { renders++; now += 3; };
  declarePanel.initialize();
  window.GemDicePerf.start();
  socketClient.sendIntentCommit('private-room', 'battle', 'source', 'private-skill', { type: 'none' });
  const row = sent.at(-1);
  assert.ok(row[1]._intent_perf_id);
  now = 20;
  handlers.get('battle_state_updated')({ _intent_perf: { id: row[1]._intent_perf_id }, phase: 'select', intents: {} });
  now = 30; ack(row);
  const result = window.GemDicePerf.report().samples[0];
  assert.equal(result.status, 'complete');
  assert.equal(result.declare_panel_ms, 3);
  assert.equal(renders, 2);
  assert.equal(store.state._intent_perf, undefined);
  assert.ok(!JSON.stringify(window.GemDicePerf.report()).includes('private-'));
  window.GemDicePerf.stop();
  declarePanel.destroy();
} else if (scenario === 'disabled') {
  send();
  assert.equal(sent[0].length, 2);
  assert.equal(sent[0][1], payload);
  assert.equal(timers.size, 0);
  let calls = 0;
  recorder.receive({}, () => { calls++; });
  recorder.render(() => { calls++; });
  assert.equal(calls, 2);
} else {
  recorder.start();
  const row = send();
  assert.notEqual(row[1], payload);
  assert.equal(payload._intent_perf_id, undefined);
  if (scenario === 'ordered' || scenario === 'ack_first') {
    if (scenario === 'ack_first') { now = 15; ack(row); }
    now = 20;
    receive(row);
    now = 30; frame();
    now = 40; frame();
    if (scenario === 'ordered') { now = 50; ack(row); }
    const result = recorder.report().samples[0];
    assert.equal(result.status, 'complete');
    assert.equal(result.store_dispatch_ms, 5);
    assert.equal(result.declare_panel_ms, 3);
    assert.equal(result.send_to_state_ms, 20);
    assert.equal(result.receive_to_frame_ms, 20);
    assert.equal(result.rtt_ms, scenario === 'ordered' ? 50 : 15);
    assert.equal(result.remaining_rtt_ms, result.rtt_ms - 5);
    assert.equal(timers.size, 0);
    assert.ok(!JSON.stringify(recorder.report()).includes('private-'));
  } else if (scenario === 'hidden') {
    visible = false;
    receive(row);
    ack(row);
    assert.equal(frames.size, 0);
    assert.equal(recorder.report().samples[0].frame_status, 'hidden');
    assert.equal(recorder.report().samples[0].receive_to_frame_ms, null);
  } else if (scenario === 'timeout') {
    for (const callback of [...timers.values()]) callback();
    const result = recorder.report().samples[0];
    assert.equal(result.status, 'timeout');
    assert.equal(result.rtt_ms, null);
    assert.equal(result.send_to_state_ms, null);
    assert.equal(recorder.report().pending, 0);
  } else if (scenario === 'stop') {
    receive(row);
    recorder.stop();
    assert.equal(timers.size, 0);
    assert.equal(frames.size, 0);
    ack(row);
    assert.equal(recorder.report().samples.length, 0);
  } else if (scenario === 'unavailable') {
    row[2]();
    assert.equal(recorder.report().samples[0].status, 'server_unavailable');
  } else if (scenario === 'isolation') {
    recorder.receive({ _intent_perf: { id: 'someone-elses-id' } }, () => { now++; });
    const other = send();
    visible = false;
    now = 10; receive(other); ack(other);
    now = 20; receive(row); ack(row);
    assert.equal(recorder.report().samples[0].send_to_state_ms, 9);
    assert.equal(recorder.report().samples[1].send_to_state_ms, 20);
    assert.equal(recorder.report().pending, 0);
  } else if (scenario === 'limits') {
    for (let index = 0; index < 100; index++) send();
    assert.equal(recorder.report().pending, 50);
    recorder.start();
    visible = false;
    for (let index = 0; index < 205; index++) { const item = send(); receive(item); ack(item); }
    assert.equal(recorder.report().samples.length, 200);
    recorder.clear();
    assert.equal(recorder.report().samples.length, 0);
  }
}
