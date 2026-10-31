// Real DOM/RAF smoke fixture; the transport and server duration are synthetic.
import { store } from '../../static/js/battle/core/BattleStore.js';
import { socketClient } from '../../static/js/battle/core/SocketClient.js';
import { declarePanel } from '../../static/js/battle/components/DeclarePanel.js';

const handlers = new Map();
const slots = {
  a: { slot_id: 'a', actor_id: 'ally', team: 'ally', initiative: 10 },
  b: { slot_id: 'b', actor_id: 'enemy', team: 'enemy', initiative: 8 },
};
const characters = [
  { id: 'ally', name: '合成の味方', type: 'ally', hp: 10, mp: 10, states: [], params: [], special_buffs: [] },
  { id: 'enemy', name: '合成の敵', type: 'enemy', hp: 10, mp: 10, states: [], params: [], special_buffs: [] },
];
window.currentUserAttribute = 'GM';
window.allSkillData = { probe: { name: '合成スキル', display_name: '合成スキル', 分類: '攻撃', target_scope: 'enemy', 基礎威力: 1, ダイス威力: '1d6' } };
window.socket = {
  connected: true, io: { engine: { transport: { name: 'synthetic' } } },
  on(name, callback) {
    if (!handlers.has(name)) handlers.set(name, []);
    handlers.get(name).push(callback);
  },
  emit(name, payload, ack) {
    if (!['battle_intent_preview', 'battle_intent_commit'].includes(name)) return;
    setTimeout(() => {
      const snapshot = {
        room_id: 'synthetic', battle_id: 'synthetic', round: 1, phase: 'select', slots,
        timeline: ['a', 'b'], intents: {
          a: { slot_id: 'a', actor_id: 'ally', skill_id: 'probe', target: payload.target, committed: name === 'battle_intent_commit' },
        },
        _intent_perf: { id: payload._intent_perf_id },
      };
      for (const callback of handlers.get('battle_state_updated') || []) callback(snapshot);
      ack?.({ intent_perf: { id: payload._intent_perf_id, handler_ms: 0, stages_ms: {}, state_emitted: true } });
      setTimeout(() => {
        document.getElementById('probe-result').textContent = JSON.stringify(window.GemDicePerf.report(), null, 2);
      }, 100);
    }, 15);
  },
};
socketClient.initialize();
store.initialize({ room_id: 'synthetic', battle_id: 'synthetic', round: 1, phase: 'select', characters, slots, intents: {}, timeline: ['a', 'b'] });
declarePanel.initialize();
document.getElementById('probe-run').onclick = () => {
  window.GemDicePerf.start();
  store.setDeclare({ sourceSlotId: 'a', targetSlotId: 'b', targetType: 'single_slot', skillId: 'probe', mode: 'idle', calc: null });
  socketClient.sendIntentPreview('synthetic', 'synthetic', 'a', 'probe', { type: 'single_slot', slot_id: 'b' });
  const refresh = () => {
    const result = window.GemDicePerf.report();
    document.getElementById('probe-result').textContent = JSON.stringify(result, null, 2);
    if (result.pending) setTimeout(refresh, 50);
  };
  setTimeout(refresh, 100);
};
