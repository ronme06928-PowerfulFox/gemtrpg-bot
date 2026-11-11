"""PR60-20: 起動時のキー移行と補正なしの定型文。"""
import json

import pytest
from sqlalchemy import event

from extensions import db
from manager.db_migration import run_auto_migration
from manager.catalog.kinds import inspect_payload
from models import CatalogDraft, CatalogEntry, CatalogHistory
from tests.test_catalog_skill import catalog
from tests.test_catalog_skill_text import run_node, ROOT

OLD = "使用時効果"
NEW = "コスト"
MODELS = (CatalogEntry, CatalogDraft, CatalogHistory)


def seed_models(kind, identifier, payload):
    db.session.add_all([
        CatalogEntry(kind=kind, entry_id=identifier, payload=payload),
        CatalogDraft(kind=kind, target_id=identifier, payload=payload, status="pending"),
        CatalogHistory(kind=kind, entry_id=identifier, revision=1, action="import", payload=payload),
    ])


def test_startup_migration_preserves_order_values_and_revisions(catalog):
    before = {"デフォルト名称": "古いスキル", OLD: "FPを2消費", "特記処理": {"cost": [{"type": "FP", "value": 2}]}}
    expected = {NEW if key == OLD else key: value for key, value in before.items()}
    seed_models("skill", "Ps-00", before)
    seed_models("buff", "Bu-99", before)
    db.session.commit()

    def no_second_update(_conn, _cursor, statement, _parameters, _context, _many):
        assert not statement.lstrip().upper().startswith("UPDATE CATALOG_")

    for attempt in range(2):
        if attempt:
            event.listen(db.engine, "before_cursor_execute", no_second_update)
        try:
            run_auto_migration(catalog)
        finally:
            if attempt:
                event.remove(db.engine, "before_cursor_execute", no_second_update)
        db.session.expire_all()
        for model in MODELS:
            migrated = model.query.filter_by(kind="skill").one()
            assert list(migrated.payload.items()) == list(expected.items())
            assert model.query.filter_by(kind="buff").order_by(model.id.desc()).first().payload == before
        assert CatalogEntry.query.filter_by(kind="skill").one().revision == 1
        assert CatalogDraft.query.filter_by(kind="skill").one().status == "pending"


def test_startup_migration_rejects_dual_keys_without_partial_updates(catalog):
    seed_models("skill", "Ps-00", {OLD: "FPを2消費"})
    db.session.add(CatalogHistory(kind="skill", entry_id="Ps-01", revision=1, action="import",
                                  payload={OLD: "", NEW: ""}))
    db.session.commit()
    with pytest.raises(RuntimeError, match="catalog_history"):
        run_auto_migration(catalog)
    for model in MODELS:
        assert model.query.filter_by(kind="skill").order_by(model.id).first().payload == {OLD: "FPを2消費"}


def test_cost_sources_use_only_new_key():
    cache = json.loads((ROOT / "data/cache/skills_cache.json").read_text(encoding="utf-8"))
    assert len(cache) == 138 and all(NEW in row and OLD not in row for row in cache.values())
    assert "出血を5得る" in cache["E-14"][NEW]
    paths = [ROOT / "tests/fixtures/skill_text_legacy.json", ROOT / "scripts/resolve_preview/skills.mjs",
             *(ROOT / "scripts/catalog_preview").rglob("*")]
    for path in paths:
        if path.suffix in {".js", ".py", ".mjs", ".json", ".html"}:
            assert OLD not in path.read_text(encoding="utf-8"), path


def test_no_correction_matches_server_browser_palette_and_reader(catalog):
    from manager.catalog.skills import omits_correction
    notes = json.loads((ROOT / "data/skill_no_correction_notes.json").read_text(encoding="utf-8"))
    cases = []
    for category, word_id, note in [("物理", "W-53", notes["物理"]), ("魔法", "W-54", notes["魔法"])]:
        label = f"{category}補正"
        wrong = "魔法" if category == "物理" else "物理"
        for classification, value, expected in [
            (category, note, True), (category, note.rstrip("。"), True),
            (category, note.replace(label, f"[[{word_id}|{label}]]"), True),
            (category, f"このスキルは対象を選択しない。{note}", True),
            (category, f"例：{note}", False), (wrong, note, False),
            ("補助", note, False), (category, "", False),
        ]:
            assert omits_correction(classification, value) == expected
            correction = "" if expected or classification == "補助" else f"+1d{{{classification}補正}}"
            payload = {"分類": classification, "特記": value, "基礎威力": "8", "ダイス威力": "+1d6",
                       "コスト": "FPを2消費", "デフォルト名称": "試験",
                       "チャットパレット": f"8+1d6{correction} 【E-26 試験】"}
            problems = inspect_payload("skill", payload, stage="draft", entry_id="E-26")
            assert not any(row["field"] == "チャットパレット" for row in problems)
            cases.append([payload, expected])
    run_node("const cases = " + json.dumps(cases, ensure_ascii=False) + ";\n" + r"""
for (const name of ['skill_effects','skill_inputs','editor','skill']) vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
for (const [payload, expected] of cases) {
  assert.equal(window.CatalogSkillNotes.omitsCorrection(payload.分類,payload.特記),expected);
  assert.equal(window.CatalogSkill.palette(payload,'E-26'),payload.チャットパレット);
  if (expected) {
    const parsed=reader.parse({category:payload.分類,cost:payload.コスト,note:payload.特記});
    assert.equal(parsed.errors.length,0);
    assert.equal(parsed.rule.cost[0].value,2);
    assert.equal(parsed.rule.power_bonus.length,0);
    const ordinaryNote = payload.特記.startsWith('このスキルは対象を選択しない。') ? 'このスキルは対象を選択しない。' : '';
    assert.deepEqual(parsed,reader.parse({cost:payload.コスト,note:ordinaryNote}));
  }
}
const wrong=cases[0][0];
assert.equal(reader.parse({category:'魔法',note:wrong.特記}).errors[0].column,'特記');
assert.equal(reader.parse({cost:'不明なコスト'}).errors[0].column,'コスト');
""")
