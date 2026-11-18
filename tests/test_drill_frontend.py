"""Drill visibility and cancellation are executable browser-independent contracts."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def node(script):
    result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,
        capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_encyclopedia_visibility_is_reused():
    node(r"""
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
const window={CatalogSkill:{groups:[['敵',[['E','敵スキル']]]]}};
for(const name of ['encyclopedia/data','drill/data']) vm.runInNewContext(fs.readFileSync('static/js/'+name+'.js','utf8'),{window});
const masters={skill:{'E-01':{},'E-02':{marks:['known']},'E-03':{marks:['hollow','known']},'Ps-00':{}}};
const extra={can_view_all:false,encounters:[],units:[{entry_id:'U-001',visibility:'public',payload:{allow_enemy:true}},
 {entry_id:'U-002',visibility:'public',payload:{allow_enemy:true,marks:['known']}}]};
let rows=window.DrillData.readable(masters,extra);
assert.deepEqual(Array.from(rows.skill,r=>r.id),['E-02','Ps-00']);
assert.deepEqual(Array.from(rows.enemy,r=>r.id),['U-002']);
rows=window.DrillData.readable(masters,{...extra,can_view_all:true});
assert.equal(rows.skill.length,4); assert.equal(rows.enemy.length,2);
assert.deepEqual(Array.from(window.DrillData.heldSkills({commands:'1d6 【E-01 secret】\n2d6 【Ps-00 name】'},rows.skill),r=>r.id),['E-01','Ps-00']);
""")


def test_calculation_drops_stale_responses_and_cleans_up():
    node(r"""
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
const window={}; vm.runInNewContext(fs.readFileSync('static/js/drill/calculation.js','utf8'),{window,setTimeout,clearTimeout,AbortController});
const pending=[],shown=[],errors=[];
const calculation=window.createDrillCalculation({delay:0,request:(body,signal)=>new Promise(resolve=>pending.push({body,signal,resolve})),
 onResult:r=>shown.push(r),onError:e=>errors.push(e),onPending:()=>{}});
const tick=()=>new Promise(resolve=>setTimeout(resolve,8));
calculation.schedule({id:1}); await tick(); calculation.schedule({id:2});
assert.equal(pending[0].signal.aborted,true); await tick();
pending[1].resolve('new'); await tick(); pending[0].resolve('old'); await tick();
assert.deepEqual(shown,['new']); assert.equal(errors.length,0);
calculation.schedule({id:3}); calculation.destroy(); await tick(); assert.equal(pending.length,2);
""")


def test_entry_bundle_and_responsive_token_contract():
    screens=(ROOT/'static/js/app_screens.js').read_text(encoding='utf-8')
    assert "['drill', 'citrine', '演習場', '勝率を試す']" in screens
    assert 'mountDrill(host, options)' in screens
    build=(ROOT/'scripts/build_frontend.mjs').read_text(encoding='utf-8')
    assert build.index("'js/encyclopedia/data.js'") < build.index("'js/drill/data.js'")
    for name in ('data','calculation','view','workspace'):
        assert f"'js/drill/{name}.js'" in build
    css=(ROOT/'static/css/modules/drill.css').read_text(encoding='utf-8')
    assert ':root' not in css and '@media' in css and 'var(--ui-' in css
    assert "@import 'css/modules/drill.css';" in (ROOT/'static/styles.css').read_text(encoding='utf-8')
