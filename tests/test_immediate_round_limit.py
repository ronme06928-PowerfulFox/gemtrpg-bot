from copy import deepcopy
from pathlib import Path
import subprocess
from types import SimpleNamespace

from manager.battle import common_manager, duel_solver
from tests.test_select_resolve_smoke import _base_state, _make_actor, _state_value
from tests.test_cost_payment_order import _skill, _update_stat


def _setup(monkeypatch):
    actor = _make_actor('A1', 'ally')
    actor['states'] = [{'name': 'FP', 'value': 20}]
    actor['flags'] = {'other_flag': True}
    actor['hasActed'] = True
    state = _base_state([actor])
    state['play_mode'] = 'battle_only'
    state['is_round_ended'] = False
    skill = _skill('INSTANT', 0, fp=2, mp=3)
    skill['tags'] = ['即時発動']
    emitted = []
    snapshots = []
    monkeypatch.setattr(duel_solver, 'all_skill_data', {'INSTANT': skill})
    monkeypatch.setattr(duel_solver, 'get_room_state', lambda _room: state)
    monkeypatch.setattr(duel_solver, '_update_char_stat', _update_stat)
    monkeypatch.setattr(duel_solver, 'broadcast_log', lambda *a, **k: None)
    monkeypatch.setattr(duel_solver, 'broadcast_state_update', lambda *a: snapshots.append(deepcopy(state)))
    monkeypatch.setattr(duel_solver, 'save_specific_room_state', lambda *a: None)
    monkeypatch.setattr(duel_solver, 'socketio', SimpleNamespace(emit=lambda *a, **k: emitted.append(a)))
    monkeypatch.setattr(common_manager, 'get_room_state', lambda _room: state)
    monkeypatch.setattr(common_manager, 'save_specific_room_state', lambda *a: None)
    monkeypatch.setattr(common_manager, 'broadcast_log', lambda *a, **k: None)
    monkeypatch.setattr(common_manager, 'broadcast_state_update', lambda *a: snapshots.append(deepcopy(state)))
    monkeypatch.setattr(common_manager, 'emit_select_resolve_events', lambda *a, **k: None)
    monkeypatch.setattr(common_manager, 'emit', lambda *a, **k: emitted.append(a))
    monkeypatch.setattr(common_manager, '_safe_emit', lambda *a, **k: emitted.append(a))
    from manager import room_manager
    monkeypatch.setattr(room_manager, 'save_specific_room_state', lambda *a: None)
    return state, actor, emitted, snapshots


def _use():
    duel_solver.handle_skill_declaration('room_t', {
        'actor_id': 'A1', 'target_id': 'A1', 'skill_id': 'INSTANT',
        'commit': True, 'prefix': 'immediate',
    }, 'tester')


def test_second_immediate_in_same_round_is_rejected_without_payment(monkeypatch):
    state, actor, emitted, _snapshots = _setup(monkeypatch)
    _use()
    assert actor['flags']['immediate_action_used'] is True
    assert actor['mp'] == 47
    _use()
    assert actor['mp'] == 47
    assert _state_value(actor, 'FP') == 18
    assert state['timeline'] == []  # immediate never consumes an ordinary slot
    assert any('1ラウンドに1回' in str(event) for event in emitted)


def test_new_round_allows_immediate_again_and_broadcasts_unset_flag(monkeypatch):
    state, actor, _emitted, snapshots = _setup(monkeypatch)
    _use()
    assert common_manager.process_full_round_end('room_t', 'tester') is True
    assert common_manager.process_round_start('room_t', 'tester') is True
    assert state['round'] == 2
    assert not actor['flags'].get('immediate_action_used')
    assert actor['flags']['other_flag'] is True
    assert not snapshots[-1]['characters'][0]['flags'].get('immediate_action_used')
    _use()
    assert actor['mp'] == 44
    assert _state_value(actor, 'FP') == 16


def test_rejected_round_start_does_not_restore_immediate(monkeypatch):
    _state, actor, _emitted, _snapshots = _setup(monkeypatch)
    _use()
    assert common_manager.process_round_start('room_t', 'tester') is False
    assert actor['flags']['immediate_action_used'] is True


def test_action_dock_and_immediate_row_reenable_from_updated_character_state():
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
function element(tag) {
  const classes = new Set();
  return {
    tag, children: [], style: {},
    classList: { add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x) },
    appendChild(child) { this.children.push(child); },
  };
}
const icon = element('div');
global.document = {
  getElementById: id => id === 'dock-immediate-icon' ? icon : null,
  createElement: element,
};
global.window = { allSkillData: { INSTANT: { tags: ['即時発動'] } }, canShowRoundControls: () => false };
global.currentUsername = 'tester';
global.currentUserId = 'u1';
global.battleState = { mode: 'battle', characters: [] };
vm.runInThisContext(fs.readFileSync('static/js/action_dock.js', 'utf8'));
isCurrentUserGM = () => false;
const char = { id: 'A1', name: 'A1', owner: 'tester', hp: 100, commands: '【INSTANT instant】', flags: { immediate_action_used: true } };
battleState.characters = [char];
updateActionDock();
assert.ok(icon.classList.contains('disabled'));
let row = createImmediateCharRow(char);
assert.ok(row.children.find(child => child.tag === 'button').disabled);
// Apply the next-round server character snapshot and refresh the existing icon.
battleState = { mode: 'battle', characters: [{ ...char, flags: {} }] };
updateActionDock();
assert.ok(icon.classList.contains('active'));
assert.ok(!icon.classList.contains('disabled'));
row = createImmediateCharRow(battleState.characters[0]);
assert.ok(!row.children.find(child => child.tag === 'button').disabled);
"""
    result = subprocess.run(
        ['node', '-e', script], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
