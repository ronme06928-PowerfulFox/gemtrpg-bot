"""PR60-7: バフのDB正本・段階別検査・管理API。"""
import copy
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from app import create_app
from extensions import db, all_buff_data, all_glossary_data, all_skill_data
from models import User, CatalogEntry, CatalogDraft, CatalogHistory
from manager.cache_paths import BUFF_CATALOG_CACHE_FILE, load_json_cache
from manager.catalog import repository as repo
from manager.catalog.kinds import CatalogValidationError, inspect_payload, validate_payload
from manager.catalog.references import find_references
from manager.buff_catalog import get_buff_by_id


@pytest.fixture
def catalog():
    app = create_app(config={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
                             "SQLALCHEMY_ENGINE_OPTIONS": {}},
                     run_startup=False, register_sockets=False)
    memories = [all_buff_data, all_glossary_data, all_skill_data]
    saved = [copy.deepcopy(data) for data in memories]
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id="admin", name="管理者", is_app_admin=True),
            User(id="author", name="制作者", is_catalog_author=True),
            User(id="reader", name="一般")])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()
    for data, old in zip(memories, saved):
        data.clear()
        data.update(old)


def connection(app, actor):
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(user_id=actor, username=actor, auth_version=1)
    return client


@pytest.mark.parametrize("data,field", [({}, "name"), ({"name": ""}, "name"),
    ({"name": "新規", "category": "バフ"}, "category"),
    ({"name": "新規", "effect": []}, "effect"),
    ({"name": "新規", "display_name": 1}, "display_name"),
    *[({"name": "新規", "default_duration": duration}, "default_duration")
      for duration in (0, -2, True, 1.5, "1")],
    ({"name": "新規", "effect": {"type": "plugin", "name": "provoke"}}, "effect.type")])
def test_buff_shape_problems(catalog, data, field):
    for stage in ("draft", "submit", "approve"):
        problems = inspect_payload("buff", data, entry_id="Bu-99", stage=stage)
        assert any(p["level"] == "error" and p["field"] == field for p in problems)
    with pytest.raises(CatalogValidationError) as error:
        validate_payload("buff", data, entry_id="Bu-99")
    assert field in error.value.errors


def test_plugin_is_checked_by_buff_id(catalog):
    """戦闘はプラグインをバフIDで呼ぶ。effect.name は判定に使わない。"""
    plugin = {"name": "新規", "effect": {"type": "plugin", "name": "どんな名前でも"}}
    assert not inspect_payload("buff", plugin, entry_id="Bu-07", stage="approve")
    for stage in ("draft", "submit"):
        problems = inspect_payload("buff", plugin, entry_id="X-0000abcd", stage=stage)
        assert [p["level"] for p in problems if p["field"] == "effect.type"] == ["warning"]
    problems = inspect_payload("buff", plugin, entry_id="Bu-99", stage="approve")
    assert [p["level"] for p in problems if p["field"] == "effect.type"] == ["error"]


def test_seed_once_and_live_reads(catalog):
    reference = all_buff_data
    assert repo.seed_kind_if_empty("buff") == 53
    repo.load_kind_into_memory("buff")
    cache = load_json_cache(BUFF_CATALOG_CACHE_FILE)
    assert all_buff_data is reference and len(reference) == 53
    assert reference == cache
    assert CatalogHistory.query.filter_by(kind="buff", action="import").count() == 53
    assert repo.seed_kind_if_empty("buff") == 0
    assert CatalogHistory.query.count() == 53
    reference.clear()
    assert len(catalog.test_client().get("/api/get_buff_data").json) == 53
    draft = repo.create_draft("buff", "author", target_id="Bu-00")
    before = get_buff_by_id("Bu-00")
    repo.update_draft(draft.id, {**draft.payload, "display_name": "改訂", "default_duration": -1})
    repo.submit_draft(draft.id)
    repo.approve_draft(draft.id, "admin")
    assert get_buff_by_id("Bu-00")["display_name"] == "改訂"
    assert before["display_name"] != "改訂"
    repo.set_deprecated("buff", "Bu-00", True, "admin")
    assert get_buff_by_id("Bu-00")["deprecated"] is True
    assert get_buff_by_id("Bu-00")["default_duration"] == -1


def test_internal_name_duplicate_and_immutable(catalog):
    repo.seed_kind_if_empty("buff")
    row = CatalogEntry.query.filter_by(kind="buff", entry_id="Bu-00").one()
    for entry_id, data in (("Bu-99", {"name": row.payload["name"]}),
                           ("Bu-00", {**row.payload, "name": "変更不可"})):
        assert any(p["field"] == "name" for p in
            inspect_payload("buff", data, entry_id=entry_id, stage="submit"))
    assert not inspect_payload("buff", row.payload, entry_id="Bu-00", stage="approve")


def test_approval_rechecks_internal_name_and_keeps_failed_draft(catalog):
    first, second = [repo.create_draft("buff", "author") for _ in range(2)]
    for draft in (first, second):
        repo.update_draft(draft.id, {"name": "同じ内部名"})
        repo.submit_draft(draft.id)
    repo.approve_draft(first.id, "admin", entry_id="Bu-99")
    before = copy.deepcopy(all_buff_data)
    with pytest.raises(CatalogValidationError) as error:
        repo.approve_draft(second.id, "admin", entry_id="Bu-100")
    assert "name" in error.value.errors
    assert second.status == "pending" and all_buff_data == before
    assert CatalogHistory.query.count() == 1


def test_inspection_references_and_stages(catalog):
    repo.seed_kind_if_empty("glossary")
    repo.set_deprecated("glossary", "W-08", True, "admin")
    data = {"name": "新規", "description": "[[W-08|廃止]] [[W-9999]]"}
    problems = inspect_payload("buff", data, entry_id=None, stage="submit")
    assert {p["level"] for p in problems} == {"warning", "error"}
    assert all(p["field"] == "description" for p in problems)
    draft = repo.create_draft("buff", "author")
    repo.update_draft(draft.id, data)
    with pytest.raises(CatalogValidationError):
        repo.submit_draft(draft.id)
    assert draft.status == "draft"
    glossary_draft = repo.create_draft("glossary", "author")
    repo.update_draft(draft.id, {"name": "新規", "description": f"[[{glossary_draft.target_id}|仮]]"})
    repo.submit_draft(draft.id)
    with pytest.raises(CatalogValidationError) as exc:
        repo.approve_draft(draft.id, "admin", entry_id="Bu-99")
    assert "description" in exc.value.errors
    repo.update_draft(glossary_draft.id, {"display_name": "用語", "category": "ルール"})
    repo.submit_draft(glossary_draft.id)
    repo.approve_draft(glossary_draft.id, "admin", entry_id="W-9999")
    assert draft.payload["description"] == "[[W-9999|仮]]"
    repo.approve_draft(draft.id, "admin", entry_id="Bu-99")
    assert get_buff_by_id("Bu-99")["effect"] == {}
    assert get_buff_by_id("Bu-99")["default_duration"] == 1
    assert inspect_payload("buff", {"name": "別", "flavor": "[[X-deadbeef]]"},
        entry_id=None, stage="submit")[0]["level"] == "error"


def test_deprecated_reference_warns_but_can_publish(catalog):
    repo.seed_kind_if_empty("glossary")
    repo.set_deprecated("glossary", "W-08", True, "admin")
    data = {"display_name": "新規", "category": "ルール", "links": ["W-08"],
            "short": "[[W-08]]"}
    assert {p["level"] for p in inspect_payload("glossary", data,
        entry_id=None, stage="approve")} == {"warning"}
    draft = repo.create_draft("glossary", "author")
    repo.update_draft(draft.id, data)
    repo.submit_draft(draft.id)
    repo.approve_draft(draft.id, "admin", entry_id="W-99")


def test_buff_api_permissions_problems_and_approval(catalog):
    author, admin, reader = [connection(catalog, who) for who in ("author", "admin", "reader")]
    assert reader.post("/api/catalog/buff/drafts", json={}).status_code == 403
    result = author.post("/api/catalog/buff/drafts", json={})
    assert result.status_code == 200
    draft_id = result.json["id"]
    assert result.json["problems"][0]["field"] == "name"
    url = f"/api/catalog/drafts/{draft_id}"
    assert author.put(url, json={"payload": {"name": "新規", "default_duration": 0}}).status_code == 200
    failed = author.post(url + "/submit")
    assert failed.status_code == 422 and "default_duration" in failed.json["errors"]
    assert author.put(url, json={"payload": {"name": "新規"}}).json["problems"] == []
    assert author.post(url + "/submit").status_code == 200
    assert author.post(url + "/approve", json={"entry_id": "Bu-99"}).status_code == 403
    assert admin.post(url + "/approve", json={"entry_id": "Bu-99"}).status_code == 200
    assert get_buff_by_id("Bu-99")["name"] == "新規"
    assert "drafts" not in reader.get("/api/catalog/buff").json


def test_buff_references_include_json_strings_and_all_sources(catalog, monkeypatch):
    import json
    from manager.items.loader import item_loader
    from manager.passives.loader import passive_loader
    from manager.radiance.loader import radiance_loader
    repo.seed_kind_if_empty("buff")
    all_skill_data.clear()
    all_skill_data["Ps-00"] = {"特記処理": json.dumps({"effects": [{"buff_id": "Bu-00"},
                                             {"buff_name": "鋭敏"}]}, ensure_ascii=False)}
    for loader in (item_loader, passive_loader, radiance_loader):
        monkeypatch.setattr(loader, "_cache", {"example": {"effect": {"buff_id": "Bu-00"}}})
    refs = find_references("buff", "Bu-00")
    assert {row["kind"] for row in refs} == {"skill", "item", "passive", "radiance"}
    assert {row["path"] for row in refs if row["kind"] == "skill"} == {
        "特記処理.effects[0].buff_id", "特記処理.effects[1].buff_name"}
    assert find_references("buff", "Bu-9999") == []


def test_buff_references_can_read_caches_without_fetching_sheets(catalog, monkeypatch):
    import manager.cache_paths as paths
    from manager.items.loader import item_loader
    from manager.passives.loader import passive_loader
    from manager.radiance.loader import radiance_loader
    repo.seed_kind_if_empty("buff")
    all_skill_data.clear()
    for loader in (item_loader, passive_loader, radiance_loader):
        monkeypatch.setattr(loader, "_cache", None)
    monkeypatch.setattr(paths, "load_json_cache", lambda _: {"cached": {"buff_id": "Bu-00"}})
    assert {ref["kind"] for ref in find_references("buff", "Bu-00")} == {
        "skill", "item", "passive", "radiance"}


def test_items_read_current_buff_dictionary(catalog, monkeypatch):
    from plugins.items.buff import BuffEffect
    from plugins.buffs.registry import buff_registry
    monkeypatch.setattr(buff_registry, "get_handler", lambda _: None)
    all_buff_data["Bu-99"] = {"name": "DBのバフ", "default_duration": -1}
    target = {"name": "対象"}
    result = BuffEffect().apply({}, target, {}, {"buff_id": "Bu-99"}, {})
    assert result["success"]
    assert target["special_buffs"][0]["name"] == "DBのバフ"
    assert target["special_buffs"][0]["lasting"] == -1


def test_standalone_lint_loads_published_buffs_from_db(catalog, monkeypatch, capsys):
    import json
    import scripts.skill_catalog_tool as tool
    draft = repo.create_draft("buff", "author")
    repo.update_draft(draft.id, {"name": "DB独自バフ"})
    repo.submit_draft(draft.id)
    repo.approve_draft(draft.id, "admin", entry_id="Bu-999")
    all_buff_data.clear()
    monkeypatch.setattr(tool, "load_skills", lambda: {"Ps-99": {"特記処理": json.dumps({
        "schema": "skill_json_rule_v2", "effects": [{"timing": "HIT", "type": "APPLY_BUFF",
            "target": "self", "buff_id": "Bu-999", "lasting": 1}]})}})
    assert tool.main(["lint", "--json"]) == 0
    assert get_buff_by_id("Bu-999")["name"] == "DB独自バフ"


def test_standalone_lint_initializes_only_buffs_without_app_context(monkeypatch, capsys):
    import json
    import app as app_module
    import scripts.skill_catalog_tool as tool
    app = create_app(config={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {}}, run_startup=False, register_sockets=False)
    before = copy.deepcopy(all_buff_data)
    all_buff_data.clear()
    calls = []

    def factory(**options):
        calls.append(options)
        return app

    monkeypatch.setattr(app_module, "create_app", factory)
    monkeypatch.setattr(tool, "load_skills", lambda: {})
    try:
        assert tool.main(["lint", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["errors"] == []
        assert calls == [{"run_startup": False, "register_sockets": False, "register_routes": False}]
        with app.app_context():
            assert CatalogEntry.query.filter_by(kind="buff").count() == 53
            assert CatalogEntry.query.filter_by(kind="glossary").count() == 0
    finally:
        with app.app_context():
            db.session.remove()
            db.drop_all()
        all_buff_data.clear()
        all_buff_data.update(before)
