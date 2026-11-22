from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def run(script):
    prefix=r"""
import fs from 'node:fs'; import assert from 'node:assert/strict';
const src=fs.readFileSync('static/js/battle/components/MatchOdds.js','utf8');
const {MatchOdds,ODDS_BATCH}=await import('data:text/javascript,'+encodeURIComponent(src));
const pending=[], changed=[];
const odds=new MatchOdds(body=>new Promise(resolve=>pending.push({body,resolve})),()=>changed.push(1),0);
const tick=()=>new Promise(resolve=>setTimeout(resolve,8));
const context={room:'r',battle:'b',source:'a',target:'b',opponent:['def',null],priority:null,
  skills:['one','two'],characters:[{hp:5}],intents:{}};
"""
    result=subprocess.run(['node','--input-type=module','-e',prefix+script],cwd=ROOT,
                          capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stderr


def test_stale_replies_are_ignored():
    run(r"""
odds.update(context); await tick(); odds.update({...context,characters:[{hp:4}]}); await tick();
pending[1].resolve({odds:{one:{advantage:'new'}}}); await tick();
pending[0].resolve({odds:{one:{advantage:'old'}}}); await tick();
assert.equal(odds.rows.one.advantage,'new');
""")


def test_rows_stay_while_rechecking_and_clear_on_new_scope():
    # 宣言の確定などで計算し直す間も、前の札を消さない（2026-11-19 札が一度消えて出直すと報告）。
    run(r"""
odds.update(context); await tick();
pending[0].resolve({odds:{one:{advantage:'有利'},two:{advantage:'拮抗'}}}); await tick();
odds.update({...context,characters:[{hp:3}]}); await tick();
assert.equal(odds.rows.one.advantage,'有利');
odds.update(null); assert.equal(odds.rows.one.advantage,'有利');  // a hidden frame only pauses
odds.update({...context,characters:[{hp:3}]}); await tick();
pending[2].resolve({odds:{one:{advantage:'不利'}}}); await tick();
assert.equal(odds.rows.one.advantage,'不利'); assert.equal(odds.rows.two,undefined);
odds.update({...context,characters:[{hp:3}],opponent:['other',null]});
assert.deepEqual(odds.rows,{});
odds.update(null); assert.deepEqual(odds.rows,{}); odds.destroy();
""")


def test_clear_discards_rows_and_pending_reply_when_opponent_has_no_intent():
    run(r"""
odds.update(context); await tick();
pending[0].resolve({odds:{one:{advantage:'有利'}}}); await tick();
assert.equal(odds.rows.one.advantage,'有利');

const recheck={...context,characters:[{hp:4}]};
odds.update(recheck); await tick();
const repaintCount=changed.length;
odds.clear();
assert.deepEqual(odds.rows,{});
assert.equal(odds.scope,null);
assert.equal(odds.key,null);
assert.equal(changed.length,repaintCount+1);
odds.clear();
pending[1].resolve({odds:{one:{advantage:'不利'}}}); await tick();
assert.deepEqual(odds.rows,{});
assert.equal(changed.length,repaintCount+1);

odds.update(recheck); await tick();
assert.equal(pending.length,3);
pending[2].resolve({odds:{one:{advantage:'拮抗'}}}); await tick();
assert.equal(odds.rows.one.advantage,'拮抗');
""")


def test_selected_skill_first_then_small_batches_and_no_refetch_on_reselect():
    run(r"""
const skills=Array.from({length:60},(_,i)=>'s'+i);
odds.update({...context,skills,priority:'s42'}); await tick();
assert.deepEqual(pending[0].body.skill_ids,['s42']);
pending[0].resolve({odds:{s42:{advantage:'有利'}}}); await tick();
assert.equal(odds.rows.s42.advantage,'有利');
assert.equal(pending[1].body.skill_ids.length,ODDS_BATCH); assert(!pending[1].body.skill_ids.includes('s42'));
odds.update({...context,skills,priority:'s7'}); await tick();
assert.equal(pending.length,2);
odds.destroy();
""")
