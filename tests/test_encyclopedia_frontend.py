"""Browser data policy and production entry points."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_visibility_policy():
    script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const window = {CatalogSkill:{groups:[['敵',[['E','敵スキル']]]]}};
vm.runInNewContext(fs.readFileSync('static/js/encyclopedia/data.js','utf8'), {window});
const masters = {
  skill: {'E-01':{デフォルト名称:'秘密'}, 'E-02':{marks:['known']}, 'E-03':{marks:['hollow']}, 'SYS-X':{}},
  buff: {'Bu-01':{marks:['enemy']}, 'Bu-02':{marks:['hollow','known']}, 'Bu-03':{}},
  item: {'I-01':{marks:['enemy']}},
};
const extra = {can_view_all:false, is_catalog_author:false, encounters:[
 {kind:'skill',entry_id:'E-01',first_seen_at:'2026-11-18T01:00:00Z'}
], units:[{entry_id:'U-001',visibility:'public',payload:{allow_enemy:true}},
 {entry_id:'U-002',visibility:'staff',payload:{allow_enemy:true,marks:['known']}},
 {entry_id:'U-003',visibility:'public',payload:{}}, {entry_id:'U-004',visibility:'public',payload:{allow_enemy:false}}]};
const model = window.EncyclopediaData;
let data = model.build(masters,extra,false);
assert.deepEqual(Array.from(data.rowsByKind.skill,r=>[r.id,r.met]), [['E-01',true],['E-02',true]]);
assert.equal(data.rowsByKind.skill[0].firstSeenAt,'2026-11-18T01:00:00Z');
assert.deepEqual(Array.from(data.rowsByKind.buff,r=>[r.id,r.met]),[['Bu-01',false],['Bu-03',true]]);
assert.equal(data.rowsByKind.item[0].met,false);
assert.deepEqual(Array.from(data.rowsByKind.enemy,r=>r.id),['U-001','U-003']);
data=model.build(masters,{...extra,can_view_all:true},false);
assert.equal(data.rowsByKind.skill.length,3);
assert(data.rowsByKind.skill.every(r=>r.met));
assert.equal(data.rowsByKind.enemy.length,3);
data=model.build(masters,{...extra,can_view_all:true},true);
assert.equal(data.rowsByKind.skill.length,2);
assert.equal(data.rowsByKind.enemy.length,2);
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_production_sources_and_lifecycle():
    build = (ROOT / "scripts/build_frontend.mjs").read_text(encoding="utf-8")
    for name in ("data", "art", "view", "workspace"):
        assert f"js/encyclopedia/{name}.js" in build
    css = (ROOT / "static/css/modules/encyclopedia.css").read_text(encoding="utf-8")
    assert ":root" not in css
    assert ".encyclopedia" in css
    view = (ROOT / "static/js/encyclopedia/view.js").read_text(encoding="utf-8")
    assert "document.addEventListener" not in view
    assert "2026-11-12" not in view
    assert "#audience" not in view
    assert "window.formatGlossaryMarkupToHTML =" not in view
    assert "destroy()" in view
    assert "row.gated ? `<dl class=\"encounter-date\">" in view
