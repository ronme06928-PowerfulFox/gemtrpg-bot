"""PR60-10: スキルの保存用JSON・配信辞書・検査・カテゴリ。"""
import copy
import json
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from sqlalchemy import inspect, text
from app import create_app
from extensions import db, all_skill_data, all_buff_data, all_glossary_data
from models import CatalogEntry, CatalogDraft, CatalogHistory, User
from manager.cache_paths import SKILLS_CACHE_FILE, load_json_cache
from manager.catalog import repository as repo
from manager.catalog.kinds import inspect_payload, CatalogValidationError
from manager.catalog.references import find_references
from manager.catalog.skills import from_cache, to_memory


@pytest.fixture
def catalog():
    app = create_app(config={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {}}, run_startup=False, register_sockets=False)
    memories = [all_skill_data, all_buff_data, all_glossary_data]
    saved = [copy.deepcopy(data) for data in memories]
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id="admin", name="管理者", is_app_admin=True),
            User(id="author", name="制作者", is_catalog_author=True), User(id="reader", name="一般")])
        db.session.commit()
        repo.seed_kind_if_empty("glossary")
        repo.seed_kind_if_empty("buff")
        repo.load_kind_into_memory("buff")
        yield app
        db.session.remove()
        db.drop_all()
    for data, old in zip(memories, saved):
        data.clear()
        data.update(old)


def payload(**changes):
    return {"デフォルト名称": "新規スキル", "分類": "物理", **changes}


def rule(**effect):
    return {"schema": "skill_json_rule_v2", "effects": [{"timing": "HIT", "type": "APPLY_BUFF",
        "target": "self", "buff_id": "Bu-00", "lasting": 1, **effect}]}


def client(app, actor):
    connection = app.test_client()
    with connection.session_transaction() as session:
        session.update(user_id=actor, username=actor, auth_version=1)
    return connection


def test_import_138_preserves_runtime_shape_tags_and_system_skills(catalog):
    cache = load_json_cache(SKILLS_CACHE_FILE)
    assert repo.seed_kind_if_empty("skill") == 138
    reference = all_skill_data
    repo.load_kind_into_memory("skill")
    assert reference is all_skill_data and "SYS-STRUGGLE" in reference
    assert CatalogEntry.query.filter_by(kind="skill").count() == 138
    assert CatalogHistory.query.filter_by(kind="skill").count() == 138
    assert repo.seed_kind_if_empty("skill") == 0
    for skill_id, row in cache.items():
        if skill_id.startswith("SYS-"):
            continue
        actual = copy.deepcopy(reference[skill_id])
        old = copy.deepcopy(row)
        actual["特記処理"] = json.loads(actual["特記処理"]) if actual["特記処理"] else {}
        old["特記処理"] = json.loads(old["特記処理"]) if old["特記処理"] else {}
        assert actual == old, skill_id
    assert all(isinstance(row.payload["特記処理"], dict) and "tags" not in row.payload
               and "スキルID" not in row.payload for row in CatalogEntry.query.filter_by(kind="skill"))
    reference.clear()
    result = catalog.test_client().get("/api/get_skill_data").json
    assert len([key for key in result if not key.startswith("SYS-")]) == 138
    assert "SYS-STRUGGLE" in result


def test_new_skill_prefix_api_next_number_and_system_survive_publish(catalog):
    repo.seed_kind_if_empty("skill")
    author, admin, reader = [client(catalog, actor) for actor in ("author", "admin", "reader")]
    assert reader.post("/api/catalog/skill/drafts", json={"id_prefix": "Ps"}).status_code == 403
    for body in ({}, {"id_prefix": "SYS"}, {"id_prefix": 1}):
        assert author.post("/api/catalog/skill/drafts", json=body).status_code == 422
    assert admin.get("/api/catalog/skill/next_id").status_code == 422
    next_id = admin.get("/api/catalog/skill/next_id?prefix=Ps").json["entry_id"]
    assert next_id.startswith("Ps-")
    assert int(next_id[3:]) == 1 + max(int(key[3:]) for key in load_json_cache(SKILLS_CACHE_FILE) if key.startswith("Ps-"))
    new = author.post("/api/catalog/skill/drafts", json={"id_prefix": "Ps"}).json
    assert new["id_prefix"] == "Ps" and new["problems"]
    url = f'/api/catalog/drafts/{new["id"]}'
    assert author.put(url, json={"payload": payload()}).status_code == 200
    assert author.post(url + "/submit").status_code == 200
    assert admin.post(url + "/approve", json={"entry_id": "Ms-99"}).status_code == 422
    assert admin.post(url + "/approve", json={"entry_id": next_id}).status_code == 200
    assert all_skill_data[next_id]["デフォルト名称"] == "新規スキル"
    assert "SYS-STRUGGLE" in all_skill_data
    assert CatalogEntry.query.filter(CatalogEntry.entry_id.like("SYS-%")).count() == 0


@pytest.mark.parametrize("data,field", [({}, "デフォルト名称"), (payload(分類="不明"), "分類"),
    (payload(距離="不明"), "距離"), (payload(属性="不明"), "属性"),
    (payload(基礎威力=1), "基礎威力"), (payload(特記処理=[]), "特記処理"),
    (payload(tags=[]), "tags"), (payload(特記処理={"schema": "skill_json_rule_v2", "tags": 1}), "特記処理.tags"), (payload(特記処理={"effects": []}), "特記処理.schema"),
    (payload(特記処理={"schema": "bad"}), "特記処理.schema"),
    (payload(特記処理=rule(timing="BAD")), "特記処理.effects[0].timing"),
    (payload(特記処理=rule(target="BAD")), "特記処理.effects[0].target")])
def test_skill_shape_validation(catalog, data, field):
    problems = inspect_payload("skill", data, entry_id="Ps-99", stage="submit")
    assert any(p["level"] == "error" and p["field"] == field for p in problems)
    draft = repo.create_draft("skill", "author", id_prefix="Ps")
    repo.update_draft(draft.id, data)
    with pytest.raises(CatalogValidationError):
        repo.submit_draft(draft.id)


def test_buff_draft_references_and_deprecated_warnings(catalog):
    draft_buff = repo.create_draft("buff", "author")
    repo.update_draft(draft_buff.id, {"name": "作成中バフ"})
    draft_skill = repo.create_draft("skill", "author", id_prefix="Ps")
    repo.update_draft(draft_skill.id, payload(特記処理=rule(buff_id=draft_buff.target_id)))
    repo.submit_draft(draft_skill.id)
    with pytest.raises(CatalogValidationError):
        repo.approve_draft(draft_skill.id, "admin", entry_id="Ps-99")
    repo.submit_draft(draft_buff.id)
    repo.approve_draft(draft_buff.id, "admin", entry_id="Bu-99")
    assert draft_skill.payload["特記処理"]["effects"][0]["buff_id"] == "Bu-99"
    repo.approve_draft(draft_skill.id, "admin", entry_id="Ps-99")
    repo.set_deprecated("buff", "Bu-99", True, "admin")
    problems = inspect_payload("skill", payload(特記処理=rule(buff_id="Bu-99")), entry_id="Ps-99", stage="approve")
    assert any(p["level"] == "warning" and p["field"].endswith("buff_id") for p in problems)
    missing = inspect_payload("skill", payload(特記処理=rule(buff_id="Bu-9999")), entry_id=None, stage="submit")
    assert any(p["level"] == "error" and p["field"].endswith("buff_id") for p in missing)


def test_palette_unknown_buff_name_and_market_warnings(catalog):
    data = payload(基礎威力="99", 取得コスト="1", チャットパレット="bad", 特記処理={
        "schema": "skill_json_rule_v2", "effects": [{"type": "APPLY_BUFF_FROM_CHARACTER_COUNT",
            "buff_name": "存在しない", "character_filter": {}, "value_per_character": 1}]})
    problems = inspect_payload("skill", data, entry_id="Ps-99", stage="submit")
    assert any(p["field"] == "チャットパレット" and p["level"] == "warning" for p in problems)
    assert any(p["field"].endswith("buff_name") and p["level"] == "warning" for p in problems)
    assert any("期待威力" in p["message"] and p["level"] == "warning" for p in problems)
    normal = payload(基礎威力="8", ダイス威力="+1d6", チャットパレット="8+1d6+1d{物理補正} 【Ps-99 新規スキル】")
    assert not any(p["field"] == "チャットパレット" for p in inspect_payload("skill", normal, entry_id="Ps-99", stage="submit"))


def test_skill_references_scan_values_and_nested_json(catalog, monkeypatch):
    import manager.cache_paths as paths
    from manager.items.loader import item_loader
    from manager.passives.loader import passive_loader
    from manager.radiance.loader import radiance_loader
    repo.seed_kind_if_empty("skill")
    repo.load_kind_into_memory("skill")
    all_skill_data["Ps-99"] = {"デフォルト名称": "参照元", "特記処理": '{"skill_id":"Ps-00"}'}
    for loader in (item_loader, passive_loader, radiance_loader):
        monkeypatch.setattr(loader, "_cache", {"example": {"nested": ["Ps-00"], "スキルID": "Ps-00"}})
    monkeypatch.setattr(paths, "load_json_cache", lambda _: {"summon": {"skill_ids": ["Ps-00"]}})
    refs = find_references("skill", "Ps-00")
    assert {row["kind"] for row in refs} >= {"skill", "item", "passive", "radiance", "summon"}
    assert any(row["kind"] == "item" and row["path"] == "スキルID" for row in refs)
    assert any(row["path"] == "特記処理.skill_id" and row["entry_id"] == "Ps-99" for row in refs)


def test_existing_draft_prefix_and_column_migration(catalog):
    repo.seed_kind_if_empty("skill")
    draft = repo.create_draft("skill", "author", target_id="Ms-00")
    assert draft.id_prefix == "Ms"
    db.session.execute(text("ALTER TABLE catalog_drafts DROP COLUMN id_prefix"))
    db.session.commit()
    from manager.db_migration import run_auto_migration
    run_auto_migration(catalog)
    assert "id_prefix" in {col["name"] for col in inspect(db.engine).get_columns("catalog_drafts")}


def test_effect_common_schema_has_shared_choices(catalog):
    from manager.json_rule_v2 import EFFECT_TIMINGS, EFFECT_TARGETS
    body = catalog.test_client().get("/api/effect_schemas").json
    assert body["common_fields"]["timing"]["options"] == list(EFFECT_TIMINGS)
    assert body["common_fields"]["target"]["options"] == list(EFFECT_TARGETS)
    assert set(body["common_fields"]["condition"]["fields"]) == {"source", "param", "operator", "value"}
