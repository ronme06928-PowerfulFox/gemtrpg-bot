"""Entering a room must not draw the previous room's board (E02 Part 18 §5)."""
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_room_reset_replaces_store_and_board_state():
    run_node(r"""
import assert from 'node:assert/strict';
globalThis.window = {};
const { store } = await import('./static/js/battle/core/BattleStore.js');
const { BoardPresentationCoordinator } = await import('./static/js/battle/core/BoardPresentationCoordinator.js');
const board = new BoardPresentationCoordinator({battleStore: store});
board.initialize();
store.initialize({room_name: 'old', phase: 'resolve_mass', round: 3,
  characters: [{id: 'old-token', name: 'Old', x: 1, y: 1}], slots: {s1: {}}, intents: {s1: {}}});
board.freeze('resolve-flow');

board.resetForRoom();
store.resetForRoom({room_name: 'new', round: 0, characters: [{id: 'new-token', name: 'New', x: 2, y: 2}]});

assert.deepEqual(board.state.characters.map(c => c.id), ['new-token']);
assert.deepEqual(store.state.characters.map(c => c.id), ['new-token']);
assert.deepEqual(store.state.slots, {});
assert.deepEqual(store.state.intents, {});
assert.equal(store.state.phase, 'select');
assert.equal(store.state.resolveView.status, 'idle');
""")


def test_join_room_resets_board_before_building_it():
    main = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    join = main[main.index("async function joinRoom"):main.index("function updateHeaderUserInfo")]
    order = ["battleState = initialState;", "BoardPresentationCoordinator?.resetForRoom()",
             "BattleStore?.resetForRoom(initialState)", "await loadTabContent('visual')"]
    positions = [join.index(token) for token in order]
    assert positions == sorted(positions)
