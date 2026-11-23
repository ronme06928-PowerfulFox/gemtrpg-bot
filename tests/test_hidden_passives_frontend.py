from tests.test_catalog_skill_editor import run_node
from tests.test_catalog_skill_text import run_node as run_text
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_token_reveal_badge_uses_the_name_lane_below_the_token():
    source = (ROOT / 'static/js/visual/visual_map.js').read_text(encoding='utf-8')
    css = (ROOT / 'static/css/modules/hidden_passive.css').read_text(encoding='utf-8')
    assert "nameLabel.appendChild(indicator)" in source
    assert "token.querySelector('.token-name-text')" in source
    assert "inset-block-start: calc(100% + 2px)" in css


def test_reveal_effect_uses_passive_picker():
    run_node(r"""
const html = effects.control('特殊パッシブID', 'Pa-17', {type:'passive_ref'}, '', {
  passive:[{id:'Pa-17',name:'伏せる効果'}]
});
assert.match(html, /<option value="Pa-17" selected>Pa-17 伏せる効果/);
""")


def test_public_skill_description_only_hints_at_reveal():
    run_text(r"""
const writer = window.CatalogSkillText.createWriter(fixture.references);
const result = writer.write({特記処理:{effects:[{
  type:'REVEAL_PASSIVE',timing:'PRE_MATCH',target:'self',passive_id:'Pa-9876'
}]}});
assert.match(result.発動時効果, /自分の伏せたパッシブを明かす/);
assert.doesNotMatch(JSON.stringify(result), /Pa-9876/);
assert.equal(result.unknown.length, 0);
""")


def test_cover_hides_content_and_badge_is_round_scoped():
    run_node(r"""
vm.runInContext(fs.readFileSync('static/js/fx/hidden_passive_fx.js','utf8'),context);
const fx = window.HiddenPassiveFx;
assert.match(fx.cover(), /伏せたパッシブ.*？？？/);
assert.match(fx.cover(true), /is-breaking/);
const char = {passive_revealed_round:2,passive_revealed_ids:['Pa-97']};
assert.equal(fx.newThisRound(char,{round:1}), false);
assert.equal(fx.newThisRound(char,{round:2}), true);
assert.equal(fx.newThisRound(char,{round:2,is_round_ended:true}), false);
assert.equal(fx.newThisRound(char,{round:3}), false);
""")


def test_open_details_show_current_hp_when_passive_is_revealed():
    run_node(r"""
const modals = fs.readFileSync('static/js/modals.js','utf8');
const hp = {}, max = {}, passiveRegion = {dataset:{}};
const selectors = {'.hp-box .detail-hp-current':hp,'.hp-box .detail-stat-max':max,
  '.character-modal-passives':passiveRegion};
const modal = {isConnected:true,dataset:{charId:'boss'},querySelector:selector=>selectors[selector]};
context.document = {querySelector:()=>modal};
context.renderCharacterPassives = (_char, ids) => ids.join(',');
context.previous = {characters:[{id:'boss',hp:80,maxHp:80,SPassive:[],hidden_passive_count:1}]};
context.battleState = {round:2,characters:[{id:'boss',hp:40,maxHp:80,SPassive:['Pa-97'],
  hidden_passive_count:0,passive_revealed_round:2,passive_revealed_ids:['Pa-97']}]};
window.allPassiveData = {'Pa-97':{}};
vm.runInContext(fs.readFileSync('static/js/fx/hidden_passive_fx.js','utf8'),context);
vm.runInContext(modals.slice(modals.indexOf('function passiveDetailSignature'),modals.indexOf('function renderCharacterCard')),context);
await vm.runInContext('refreshOpenCharacterPassives(previous,battleState)',context);
assert.equal(hp.textContent,40);
assert.equal(max.textContent,'/ 80');
assert.equal(passiveRegion.innerHTML,'Pa-97');
""")
