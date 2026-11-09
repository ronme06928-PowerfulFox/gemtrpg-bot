"""PR60-13: 文章編集の位置・候補・分類によるタイミング。"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    setup = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const window={};const context=vm.createContext({window,console});
for(const name of ['glossary','text_tools'])vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
const tools=window.CatalogTextTools;
const term={entry_id:'W-01',payload:{display_name:'出血',category:'状態異常',synonyms:['別の名前']}};
const clean=value=>JSON.parse(JSON.stringify(value));
"""
    result = subprocess.run(['node', '--input-type=module', '-e', setup + script], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cursor_selection_and_inline_opening_replacement():
    run_node(r"""
assert.deepEqual(clean(tools.insertLink('前後',1,1,term)),{value:'前[[W-01|出血]]後',caret:12});
assert.deepEqual(clean(tools.insertLink('前傷あと後',1,4,term)),{value:'前[[W-01|傷あと]]後',caret:13});
const text='前[[出血後';
assert.deepEqual(clean(tools.insertLink(text,5,5,term,1)),{value:'前[[W-01|出血]]後',caret:12});
assert.deepEqual(clean(tools.inlineQuery('前[[出',4,4)),{start:1,query:'出'});
assert.equal(tools.inlineQuery('[[W-01|出血]]',11,11),null);
assert.equal(tools.inlineQuery('[[出血\n次',6,6),null);
assert.equal(tools.inlineQuery('選択',0,2),null);
""")


def test_timing_only_changes_current_line_and_replaces_existing_prefix():
    run_node(r"""
const timing={entry_id:'W-26',payload:{display_name:'ラウンド終了時'}};
for(const prefix of ['', '(的中時):', '([[W-19|使用時]]):', '  (的中時)： ']) {
 const text='前行\n'+prefix+'自身のFPを2回復。\n後行';
 const result=tools.insertTiming(text,text.indexOf('FP'),timing);
 assert.equal(result.value,'前行\n([[W-26|ラウンド終了時]]):自身のFPを2回復。\n後行');
 assert.equal(result.caret,result.value.indexOf('自身'));
}
assert.equal(tools.insertTiming('\n次',0,timing).value,'([[W-26|ラウンド終了時]]):\n次');
assert.equal(tools.insertTiming('',0,timing).value,'([[W-26|ラウンド終了時]]):');
""")


def test_reuses_link_candidates_and_timing_classification_not_fixed_ids():
    run_node(r"""
const rows=[term,{...term,entry_id:'W-02',deprecated:true},
 {entry_id:'W-99',payload:{category:'タイミング',display_name:'追加時',sort_order:2}},
 {entry_id:'W-100',payload:{category:'タイミング',display_name:'最初',sort_order:1}},
 {entry_id:'W-98',payload:{category:'タイミング',display_name:'同順',sort_order:2}},
 {entry_id:'W-97',payload:{category:'タイミング',display_name:'未指定',sort_order:null}}];
let called=false;const original=window.CatalogGlossary.linkCandidates;
window.CatalogGlossary.linkCandidates=(...args)=>{called=true;return original(...args);};
assert.deepEqual(clean(tools.candidates(rows,'W-99','別の名前')).map(row=>row.entry_id),['W-01']);
assert.equal(called,true);
assert.equal(tools.candidates(rows,'W-01','出血').length,0);
assert.deepEqual(clean(tools.timings(rows)).map(row=>row.entry_id),['W-100','W-98','W-99','W-97']);
assert.deepEqual(clean(tools.timings([{...rows[2],deprecated:true}])),[]);
""")


def test_prose_fields_only_and_no_json_fields_marked():
    run_node(r"""
for(const name of ['buff','skill_text_help','skill_text','skill_effects','skill'])vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
const glossary=window.CatalogGlossary.form(window.CatalogGlossary.defaults());
const buff=window.CatalogBuff.form(window.CatalogBuff.defaults());
window.CatalogSkill.configure({effect_types:{},custom_effects:{},common_fields:{}},{});
const skill=window.CatalogSkill.form(window.CatalogSkill.defaults());
const text=window.CatalogSkillText.renderForm({},'',null,{});
for(const [html,count] of [[glossary,3],[buff,2],[skill,4],[text,3]]) {
 assert.equal((html.match(/data-catalog-text/g)||[]).length,count);
 assert.ok(!/<textarea[^>]*data-catalog-text[^>]*(?:cat-effect-source|spellcheck)/.test(html));
}
""")


def test_mounted_picker_caret_input_keyboard_ime_and_cleanup():
    run_node(r"""
class Element {
 constructor(){this.listeners=new Map();this.attrs={};this.dataset={};this.hidden=false;this.value='';this.selectionStart=0;this.selectionEnd=0;}
 addEventListener(type,handler){if(!this.listeners.has(type))this.listeners.set(type,[]);this.listeners.get(type).push(handler);}
 removeEventListener(type,handler){this.listeners.set(type,this.listeners.get(type).filter(fn=>fn!==handler));}
 getAttribute(k){return this.attrs[k]??null;}closest(){return null;}
 setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}
 focus(){this.focused=true;}setSelectionRange(a,b){this.selectionStart=a;this.selectionEnd=b;}
 dispatchEvent(event){for(const fn of this.listeners.get(event.type)||[])fn(event);}
 querySelector(selector){return this.nodes?.[selector]||null;}
 before(node){this.toolbar=node;}remove(){this.removed=true;}contains(target){return Object.values(this.nodes||{}).includes(target);}
}
const field=new Element(),root=new Element(),toolbar=new Element(),label=new Element();
label.childNodes=[{nodeType:3,textContent:'発動時効果'}];field.closest=()=>label;
const button=new Element(),timing=new Element(),picker=new Element(),search=new Element(),list=new Element();
toolbar.nodes={'[data-text-insert]':button,'[data-text-timing]':timing,'.cat-text-picker':picker,'input':search,'[role="listbox"]':list};
picker.hidden=true;root.querySelectorAll=()=>[field];field.ownerDocument={createElement:()=>toolbar,defaultView:{Event:class {constructor(type,options){this.type=type;Object.assign(this,options);}}}};
let changes=0;field.addEventListener('input',()=>changes++);
const authoring=tools.mount(root,{entries:[term],currentId:'W-99'});
assert.equal(field.getAttribute('aria-label'),'発動時効果');assert.equal(label.getAttribute('for'),field.id);
const event=(target,type,extra={})=>target.dispatchEvent({type,target,preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;},...extra});
field.value='前傷後';field.setSelectionRange(1,2);
event(field,'blur');event(button,'click');assert.equal(picker.hidden,false);assert.ok(search.focused);
search.value='別の名前';event(search,'input');assert.match(list.innerHTML,/W-01/);
event(search,'keydown',{key:'Enter',isComposing:true});assert.equal(changes,0);
event(search,'keydown',{key:'Enter'});assert.equal(field.value,'前[[W-01|傷]]後');assert.equal(field.selectionStart,11);assert.equal(changes,1);assert.equal(picker.hidden,true);
field.value='前[[';field.setSelectionRange(3,3);event(field,'input');assert.equal(picker.hidden,false);
event(field,'keydown',{key:'ArrowDown'});event(field,'keydown',{key:'Enter'});
assert.equal(field.value,'前[[W-01|出血]]');assert.equal(changes,3);
event(button,'click');event(search,'keydown',{key:'Escape'});assert.equal(picker.hidden,true);
authoring.destroy();authoring.destroy();assert.equal(toolbar.removed,true);assert.equal(field.getAttribute('aria-label'),null);assert.equal(label.getAttribute('for'),null);
assert.equal((button.listeners.get('click')||[]).length,0);assert.equal((root.listeners.get('pointerdown')||[]).length,0);
""")
