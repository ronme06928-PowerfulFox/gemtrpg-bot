from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def test_stale_odds_and_batch_limit():
    script=r"""
import fs from 'node:fs'; import assert from 'node:assert/strict';
const src=fs.readFileSync('static/js/battle/components/MatchOdds.js','utf8');
const {MatchOdds}=await import('data:text/javascript,'+encodeURIComponent(src));
const pending=[], changed=[];
const odds=new MatchOdds(body=>new Promise(resolve=>pending.push({body,resolve})),()=>changed.push(1),0);
const tick=()=>new Promise(resolve=>setTimeout(resolve,8));
const context={room:'r',battle:'b',source:'a',target:'b',skills:['one'],characters:[{hp:5}]};
odds.update(context); await tick(); odds.update({...context,characters:[{hp:4}]}); await tick();
pending[1].resolve({odds:{one:{advantage:'new'}}}); await tick();
pending[0].resolve({odds:{one:{advantage:'old'}}}); await tick();
assert.equal(odds.rows.one.advantage,'new'); assert.equal(changed.length,1);
odds.update({...context,skills:Array.from({length:201},(_,i)=>String(i))}); await tick();
for(let i=2;i<5;i++) { assert(pending[i].body.skill_ids.length<=100); pending[i].resolve({odds:{}}); await tick(); }
odds.update(null); assert.deepEqual(odds.rows,{}); odds.update(context); odds.destroy(); await tick();
assert.equal(pending.length,5);
"""
    result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stderr
