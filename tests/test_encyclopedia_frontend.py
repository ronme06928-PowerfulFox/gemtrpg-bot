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
  skill: {'E-01':{デフォルト名称:'秘密'}, 'E-02':{marks:['known']}, 'E-03':{}, 'SYS-X':{}},
  buff: {'Bu-01':{marks:['enemy']}, 'Bu-02':{marks:['known']}, 'Bu-03':{}},
  item: {'I-01':{marks:['enemy']}},
};
const extra = {can_view_all:false, is_catalog_author:false, encounters:[
 {kind:'skill',entry_id:'E-01',first_seen_at:'2026-11-18T01:00:00Z'}
], units:[{entry_id:'U-001',visibility:'public',payload:{allow_enemy:true}},
 {entry_id:'U-002',visibility:'staff',payload:{allow_enemy:true,marks:['known']}},
 {entry_id:'U-003',visibility:'public',payload:{}}, {entry_id:'U-004',visibility:'public',payload:{allow_enemy:false}},
 {entry_id:'U-005',visibility:'public',payload:{domain:'hollow',marks:['known']}}]};
const model = window.EncyclopediaData;
let data = model.build(masters,extra,false);
assert.deepEqual(Array.from(data.rowsByKind.skill,r=>[r.id,r.met]), [['E-01',true],['E-02',true],['E-03',false]]);
assert.equal(data.rowsByKind.skill[0].firstSeenAt,'2026-11-18T01:00:00Z');
assert.deepEqual(Array.from(data.rowsByKind.buff,r=>[r.id,r.met]),[['Bu-01',false],['Bu-02',true],['Bu-03',true]]);
assert.equal(data.rowsByKind.item[0].met,false);
assert.deepEqual(Array.from(data.rowsByKind.enemy,r=>r.id),['U-001','U-003']);
data=model.build(masters,{...extra,can_view_all:true},false);
assert.equal(data.rowsByKind.skill.length,3);
assert(data.rowsByKind.skill.every(r=>r.met));
assert.equal(data.rowsByKind.enemy.length,4);
data=model.build(masters,{...extra,can_view_all:true},true);
assert.equal(data.rowsByKind.skill.length,3);
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
    assert "variablePattern" in view and "'<var class=\"encyclopedia-variable\">X</var>'" in view
    assert ".replace(variablePattern, 'X')" in view


def test_buff_volumes_omit_empty_and_keep_uncategorized():
    script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const window={};
vm.runInNewContext(fs.readFileSync('static/js/encyclopedia/data.js','utf8'),{window});
const rows=[
 {id:'Bu-00',data:{category:'能力の増減'}},
 {id:'Bu-06',data:{category:'状態異常の強化'}},
 {id:'Bu-99',data:{}}
];
const books=window.EncyclopediaData.buffVolumes(rows);
assert.deepEqual(Array.from(books,b=>b.title),['盛衰','傷痕','雑録']);
assert.deepEqual(Array.from(books,b=>Array.from(b.rows,r=>r.id)),[['Bu-00'],['Bu-06'],['Bu-99']]);
assert.equal(new Set(books.map(b=>b.color)).size,3);
assert.equal(window.EncyclopediaData.buffVolumes([]).length,0);
"""
    result=subprocess.run(["node","--input-type=module","-e",script],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_room_entry_and_modal_lifecycle():
    room = (ROOT / 'static/js/encyclopedia/room.js').read_text(encoding='utf-8')
    workspace = (ROOT / 'static/js/encyclopedia/workspace.js').read_text(encoding='utf-8')
    view = (ROOT / 'static/js/encyclopedia/view.js').read_text(encoding='utf-8')
    assert 'dialog.showModal()' in room
    assert 'initialState:position' in room and 'getState()' in room
    assert 'savedRoom !== room' in room and 'resetRoomEncyclopedia' in room
    assert 'row.id === entryId && row.met' in room
    assert 'options.room' in workspace and 'openEntry(id)' in workspace
    assert 'restore(position)' in view and 'openEntry(id)' in view
    for path in ('action_dock.js', 'exploration/exploration_dock.js'):
        source = (ROOT / 'static/js' / path).read_text(encoding='utf-8')
        assert 'openRoomEncyclopedia()' in source
        assert 'openGlossaryCatalogModal' not in source
    glossary = (ROOT / 'static/js/common/glossary_ui.js').read_text(encoding='utf-8')
    assert "!document.querySelector('dialog[open]')" in glossary


def test_world_shelf_puts_buffs_in_one_row_after_case():
    view = (ROOT / 'static/js/encyclopedia/view.js').read_text(encoding='utf-8')
    assert "['case:バフ', ...buffKeys, 'hourglass']" in view
    assert 'class="shelf-case"' in view
    assert 'shelf-case' in (ROOT / 'static/css/modules/encyclopedia.css').read_text(encoding='utf-8')


def test_bulk_frontend_and_buff_category_controls():
    source = (ROOT / 'static/js/master_data/bulk.js').read_text(encoding='utf-8')
    assert 'base_revision' in source and 'marks_add' in source and 'marks_remove' in source
    assert '確認して公開' in source and '確認して申請' in source
    assert 'result.skipped' in source and 'row.reason' in source
    buff = (ROOT / 'static/js/master_data/buff.js').read_text(encoding='utf-8')
    assert "['category', '分類', 'category']" in buff
    assert 'filters.category' in buff
