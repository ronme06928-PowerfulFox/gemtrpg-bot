from tests.test_catalog_skill_editor import run_node
from tests.test_catalog_skill_text import run_node as run_text


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
