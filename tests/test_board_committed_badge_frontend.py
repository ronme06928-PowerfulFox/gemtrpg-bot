"""Commit-only changes must reach the board, including an attack response."""

import json
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("initial_committed", [False, True])
@pytest.mark.parametrize("frozen", [False, True])
def test_commit_and_cancel_refresh_board_without_changing_skill_or_target(initial_committed, frozen):
    script = "const config = " + json.dumps({"initial": initial_committed, "frozen": frozen}) + ";\n" + r"""
import assert from 'node:assert/strict';
import { BoardPresentationCoordinator } from './static/js/battle/core/BoardPresentationCoordinator.js';
const initial = {battle_id:'probe',round:1,phase:'select',characters:[],slots:{A:{actor_id:'A'},B:{actor_id:'B'}},
  intents:{A:{skill_id:'defend',target:{type:'single_slot',slot_id:'B'},committed:config.initial},
           B:{skill_id:'attack',target:{type:'single_slot',slot_id:'A'},committed:true}},declare:{mode:'idle'}};
let receive;
const source={state:initial,subscribe(fn){receive=fn;return ()=>{};}};
const coordinator=new BoardPresentationCoordinator({battleStore:source,events:{on(){return ()=>{};}}});
coordinator.initialize();
let notifications=0;
coordinator.subscribe(()=>notifications++);
receive(structuredClone(initial));
assert.equal(notifications,0,'unchanged board stays suppressed');
if(config.frozen)coordinator.freeze('test-transition');
const changed=structuredClone(initial);
changed.intents.A.committed=!config.initial;
source.state=changed;
receive(changed);
if(config.frozen){
  assert.equal(notifications,0,'transition keeps board frozen');
  assert.equal(coordinator.state.intents.A.committed,config.initial);
  coordinator.release('test-transition');
}
assert.equal(notifications,1,'commit-only change reaches board once');
assert.equal(coordinator.state.intents.A.committed,!config.initial);
assert.deepEqual(coordinator.state.intents.B,initial.intents.B);
receive(structuredClone(changed));
assert.equal(notifications,1,'identical snapshot does not repaint again');
coordinator.destroy();
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
