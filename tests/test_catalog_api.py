"""PR60-4: 権限境界・HTTP契約・保存処理との接続。"""
import copy
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from app import create_app
from extensions import db, all_glossary_data, all_skill_data, all_buff_data
from models import User, CatalogEntry, CatalogDraft, CatalogHistory
from manager.catalog import repository as repo


@pytest.fixture
def api():
    app = create_app(config={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
                             "SQLALCHEMY_ENGINE_OPTIONS": {}},
                     run_startup=False, register_sockets=False)
    memories = [all_glossary_data, all_skill_data, all_buff_data]
    before = [copy.deepcopy(memory) for memory in memories]
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id="admin", name="管理者", is_app_admin=True),
            User(id="author", name="制作者", is_catalog_author=True),
            User(id="other", name="別の制作者", is_catalog_author=True),
            User(id="reader", name="一般")])
        db.session.commit()
        repo.seed_kind_if_empty("glossary")
        repo.load_kind_into_memory("glossary")
        yield app
        db.session.remove()
        db.drop_all()
    for memory, saved in zip(memories, before):
        memory.clear()
        memory.update(saved)


def client(api, actor):
    connection = api.test_client()
    if actor:
        with connection.session_transaction() as session:
            session.update(user_id=actor, username=actor, auth_version=1,
                           is_app_admin=True, is_catalog_author=True)  # DBを正本にする
    return connection


def draft(target="W-08"):
    return repo.create_draft("glossary", "author", target_id=target)


READS = [("GET", "/api/catalog/glossary"),
         ("GET", "/api/catalog/overview"),
         ("GET", "/api/catalog/glossary/W-08/history"),
         ("GET", "/api/catalog/glossary/W-08/references")]
WRITES = [("POST", "/api/catalog/glossary/drafts"),
          ("PUT", "/api/catalog/drafts/{id}"),
          ("POST", "/api/catalog/drafts/{id}/submit"),
          ("DELETE", "/api/catalog/drafts/{id}"),
          ("POST", "/api/catalog/drafts/{id}/approve"),
          ("POST", "/api/catalog/drafts/{id}/reject"),
          ("POST", "/api/catalog/glossary/W-08/deprecate"),
          ("POST", "/api/catalog/glossary/W-08/restore"),
          ("GET", "/api/catalog/glossary/next_id")]


@pytest.mark.parametrize("method,url", READS + WRITES)
def test_every_route_requires_session(api, method, url):
    row = draft()
    assert client(api, None).open(url.format(id=row.id), method=method, json={}).status_code == 401


@pytest.mark.parametrize("actor", ["reader", "author", "other", "admin"])
def test_public_views_and_draft_visibility(api, actor):
    row = draft()
    connection = client(api, actor)
    response = connection.get("/api/catalog/glossary")
    assert response.status_code == 200
    assert len(response.json["entries"]) == 83
    assert ("drafts" in response.json) == (actor != "reader")
    if actor != "reader":
        assert response.json["drafts"][0]["created_by_name"] == "制作者"
    history = connection.get("/api/catalog/glossary/W-08/history")
    assert history.status_code == 200 and history.json["history"][0]["action"] == "import"
    assert connection.get("/api/catalog/glossary/W-08/references").status_code == 200


@pytest.mark.parametrize("method,url", WRITES)
def test_general_user_cannot_write_or_get_next_id(api, method, url):
    row = draft()
    assert client(api, "reader").open(url.format(id=row.id), method=method, json={}).status_code == 403


@pytest.mark.parametrize("method,suffix,body", [
    ("PUT", "", {"payload": {}}), ("POST", "/submit", {}), ("DELETE", "", {})])
def test_another_author_cannot_mutate_draft(api, method, suffix, body):
    row = draft()
    assert client(api, "other").open(f"/api/catalog/drafts/{row.id}{suffix}", method=method, json=body).status_code == 403
    assert db.session.get(CatalogDraft, row.id).status == "draft"


@pytest.mark.parametrize("url,body", [
    ("/api/catalog/drafts/{id}/approve", {}), ("/api/catalog/drafts/{id}/reject", {"reason": "却下"}),
    ("/api/catalog/glossary/W-08/deprecate", {"deprecated": True}),
    ("/api/catalog/glossary/W-08/restore", {"revision": 1})])
def test_author_cannot_approve_or_change_publication(api, url, body):
    row = draft()
    assert client(api, "author").post(url.format(id=row.id), json=body).status_code == 403
    assert client(api, "author").get("/api/catalog/glossary/next_id").status_code == 403


def test_full_draft_flow_and_broadcast_after_publication(api, monkeypatch):
    import routes.catalog as routes
    events = []
    def emit(event, data, **kwargs):
        assert all_glossary_data[data["entry_id"]]["display_name"] == "改訂した用語"
        assert CatalogHistory.query.filter_by(entry_id=data["entry_id"], revision=data["revision"]).one()
        events.append((event, data, kwargs))
    monkeypatch.setattr(routes.socketio, "emit", emit)
    author, admin = client(api, "author"), client(api, "admin")
    row = author.post("/api/catalog/glossary/drafts", json={"target_id": "W-08"}).json
    duplicate = client(api, "other").post("/api/catalog/glossary/drafts", json={"target_id": "W-08"})
    assert duplicate.json["id"] == row["id"] and CatalogDraft.query.count() == 1
    url = f"/api/catalog/drafts/{row['id']}"
    payload = {**row["payload"], "display_name": "改訂した用語"}
    assert author.put(url, json={"payload": payload}).status_code == 200
    assert author.post(url+"/submit").json["status"] == "pending"
    assert admin.post(url+"/reject", json={"reason": "説明を確認"}).json["reject_reason"] == "説明を確認"
    assert author.put(url, json={"payload": payload}).json["status"] == "draft"
    assert author.post(url+"/submit").status_code == 200
    assert not events
    response = admin.post(url+"/approve", json={})
    assert response.status_code == 200 and response.json["revision"] == 2
    assert response.json["updated_by_name"] == "管理者"
    assert events == [("catalog_updated", {"kind": "glossary", "entry_id": "W-08", "revision": 2}, {})]
    assert CatalogDraft.query.count() == 0
    assert client(api, None).get("/api/get_glossary_data").json["W-08"]["display_name"] == "改訂した用語"


def test_invalid_submission_conflict_and_no_notifications(api, monkeypatch):
    import routes.catalog as routes
    events = []
    monkeypatch.setattr(routes.socketio, "emit", lambda *args, **kwargs: events.append(args))
    author, admin = client(api, "author"), client(api, "admin")
    row = draft()
    url = f"/api/catalog/drafts/{row.id}"
    author.put(url, json={"payload": {"display_name": "bad", "category": "ルール", "links": ["W-999"]}})
    response = author.post(url+"/submit")
    assert response.status_code == 422 and "links" in response.json["errors"]
    assert row.status == "draft"
    author.put(url, json={"payload": {"display_name": "good", "category": "ルール"}})
    author.post(url+"/submit")
    assert author.put(url, json={"payload": {}}).status_code == 409
    repo.set_deprecated("glossary", "W-08", True, "admin")
    response = admin.post(url+"/approve", json={})
    assert response.status_code == 409 and "base_revision" in response.json["errors"]
    assert not events and CatalogDraft.query.count() == 1


def test_new_entry_withdraw_deprecate_restore_and_next_id(api, monkeypatch):
    import routes.catalog as routes
    events = []
    monkeypatch.setattr(routes.socketio, "emit", lambda name, data: events.append((name, data)))
    author, admin = client(api, "author"), client(api, "admin")
    assert admin.get("/api/catalog/glossary/next_id").json == {"entry_id": "W-83"}
    new = author.post("/api/catalog/glossary/drafts", json={}).json
    url = f"/api/catalog/drafts/{new['id']}"
    author.put(url, json={"payload": {"display_name": "新規", "category": "ルール"}})
    author.post(url+"/submit")
    assert admin.post(url+"/approve", json={}).status_code == 422
    assert admin.post(url+"/approve", json={"entry_id": "W-08"}).status_code == 409
    assert admin.post(url+"/approve", json={"entry_id": "W-100"}).json["revision"] == 1
    assert admin.get("/api/catalog/glossary/next_id").json == {"entry_id": "W-101"}
    assert admin.post("/api/catalog/glossary/W-100/deprecate", json={"deprecated": True}).json["revision"] == 2
    assert all_glossary_data["W-100"]["deprecated"]
    assert admin.post("/api/catalog/glossary/W-100/restore", json={"revision": 1}).json["revision"] == 3
    assert not all_glossary_data["W-100"]["deprecated"]
    assert [event[1]["revision"] for event in events] == [1, 2, 3]
    row = author.post("/api/catalog/glossary/drafts", json={}).json
    assert author.delete(f"/api/catalog/drafts/{row['id']}").json == {"id": row["id"], "withdrawn": True}


@pytest.mark.parametrize("body", [None, [], "bad", {"deprecated": "false"}, {}])
def test_malformed_body_is_422(api, body):
    response = client(api, "admin").post("/api/catalog/glossary/W-08/deprecate", json=body)
    assert response.status_code == 422 and response.is_json


def test_unknown_kind_missing_objects_and_revoked_author(api):
    connection = client(api, "admin")
    assert connection.get("/api/catalog/skills").status_code == 404
    assert connection.get("/api/catalog/glossary/W-999/history").status_code == 404
    assert connection.post("/api/catalog/drafts/999/approve", json={}).status_code == 404
    row = draft()
    user = db.session.get(User, "author")
    user.is_catalog_author = False
    db.session.commit()
    assert client(api, "author").delete(f"/api/catalog/drafts/{row.id}").status_code == 403


def test_references_find_exact_ids_in_nested_text_without_drafts(api):
    all_skill_data.clear()
    all_skill_data.update({"Ps-01": {"デフォルト名称": "技", "effects": [{"text": "[[W-08|荊棘]] / [[W-08]] / [[W-080]]"}]}})
    all_buff_data.clear()
    all_buff_data.update({"Bu-01": {"name": "バフ", "description": "[[W-08]]"}})
    response = client(api, "reader").get("/api/catalog/glossary/W-08/references")
    assert response.status_code == 200
    references = response.json["references"]
    assert any(r["kind"] == "glossary" and r["path"] == "links" for r in references)
    assert [r for r in references if r["kind"] == "skill"] == [
        {"kind": "skill", "entry_id": "Ps-01", "display_name": "技", "path": "effects[0].text"}]
    assert any(r["kind"] == "buff" and r["entry_id"] == "Bu-01" for r in references)


def test_api_delegates_payload_storage_to_repository(api, monkeypatch):
    row = draft()
    calls = []
    def save(draft_id, payload):
        calls.append((draft_id, payload))
        return row
    monkeypatch.setattr(repo, "update_draft", save)
    response = client(api, "author").put(f"/api/catalog/drafts/{row.id}", json={"payload": {"short": "未完成"}})
    assert response.status_code == 200
    assert calls == [(row.id, {"short": "未完成"})]
    assert row.payload["short"] != "未完成"



def test_broadcast_reaches_multiple_connected_lobby_clients(api):
    from extensions import socketio
    connections = [socketio.test_client(api, flask_test_client=client(api, actor))
                   for actor in ("reader", "other")]
    try:
        assert all(connection.is_connected() for connection in connections)
        for connection in connections:
            connection.get_received()
        response = client(api, "admin").post("/api/catalog/glossary/W-08/deprecate", json={"deprecated": True})
        assert response.status_code == 200
        for connection in connections:
            notifications = [event for event in connection.get_received() if event["name"] == "catalog_updated"]
            assert len(notifications) == 1
            assert notifications[0]["args"] == [{"kind": "glossary", "entry_id": "W-08", "revision": 2}]
    finally:
        for connection in connections:
            if connection.is_connected():
                connection.disconnect()


def test_admin_can_edit_submit_withdraw_and_author_can_create_new(api):
    row = draft()
    admin = client(api, "admin")
    url = f"/api/catalog/drafts/{row.id}"
    assert admin.put(url, json={"payload": row.payload}).status_code == 200
    assert admin.post(url+"/submit").status_code == 200
    assert admin.delete(url).status_code == 200
    created = admin.post("/api/catalog/glossary/drafts", json={})
    assert created.status_code == 200 and created.json["created_by"] == "admin"
    assert client(api, "other").post("/api/catalog/glossary/drafts", json={}).status_code == 200


@pytest.mark.parametrize("revision", [None, True, "1", 0, -1, 999])
def test_invalid_restore_revision_is_structured_error(api, revision):
    response = client(api, "admin").post("/api/catalog/glossary/W-08/restore", json={"revision": revision})
    assert response.status_code == 422 and "revision" in response.json["errors"]


def test_deprecate_noop_does_not_make_history_or_notification(api, monkeypatch):
    import routes.catalog as routes
    monkeypatch.setattr(routes.socketio, "emit", lambda *args, **kwargs: pytest.fail("変更なしでは通知しない"))
    response = client(api, "admin").post("/api/catalog/glossary/W-08/deprecate", json={"deprecated": False})
    assert response.status_code == 200 and response.json["revision"] == 1
    assert CatalogHistory.query.count() == 83


def test_next_id_empty_and_numeric_order(api):
    CatalogEntry.query.delete()
    db.session.commit()
    admin = client(api, "admin")
    assert admin.get("/api/catalog/glossary/next_id").json["entry_id"] == "W-00"
    db.session.add_all([CatalogEntry(kind="glossary", entry_id=entry_id, payload={}, revision=1, deprecated=True)
                        for entry_id in ("W-99", "W-100")])
    db.session.commit()
    assert admin.get("/api/catalog/glossary/next_id").json["entry_id"] == "W-101"


def test_text_references_are_authenticated_current_and_read_only(api, monkeypatch):
    from manager.summons import loader
    monkeypatch.setattr(loader, "load_summon_templates", lambda: {"U-99": {
        "name": "現在の召喚", "tag_ids": ["瓦礫"], "private_field": "配らない"}})
    path = "/api/catalog/skill/text_references"
    assert client(api, None).get(path).status_code == 401
    for actor in ("reader", "author", "admin"):
        data = client(api, actor).get(path).json
        assert data == {"summon_refs": [{"id": "U-99", "name": "現在の召喚", "tag_ids": ["瓦礫"],
            "summon_duration_mode": "permanent", "summon_duration": 0}]}
    assert CatalogDraft.query.count() == 0


def test_legacy_builder_and_its_apis_are_removed(api):
    connection = client(api, "author")
    for method, path in (("GET", "/json_builder"), ("GET", "/api/json_builder_reference"),
                         ("POST", "/api/json_nl_builder_audit"),
                         ("GET", "/chara_creator/json_definition_builder.html")):
        assert connection.open(path, method=method).status_code in (404, 405)
    routes = {rule.rule for rule in api.url_map.iter_rules()}
    assert not routes & {"/json_builder", "/api/json_builder_reference", "/api/json_nl_builder_audit"}


@pytest.mark.parametrize("actor", ["reader", "author", "admin"])
def test_overview_counts_all_kinds_and_pending_admin_only(api, actor):
    from manager.catalog.kinds import KINDS
    for kind in ["glossary", "buff", "skill", "item", "passive", "radiance", "summon"]:
        repo.seed_kind_if_empty(kind)
        if kind in ("buff", "skill"):
            repo.load_kind_into_memory(kind)
    CatalogEntry.query.filter_by(kind="glossary", entry_id="W-01").one().deprecated = True
    db.session.commit()
    repo.create_draft("glossary", "author")
    row = draft()
    repo.submit_draft(row.id)
    other = repo.create_draft("buff", "other", target_id="Bu-00")
    repo.submit_draft(other.id)
    response = client(api, actor).get("/api/catalog/overview")
    assert response.status_code == 200
    data = response.json
    assert set(data["counts"]) == set(KINDS)
    assert data["counts"]["glossary"]["published"] == 82
    assert data["counts"]["glossary"]["deprecated"] == 1
    assert data["counts"]["skill"]["published"] == 138
    if actor == "reader":
        assert "pending" not in data
        assert set(data["counts"]["buff"]) == {"published", "deprecated"}
    else:
        assert data["counts"]["buff"]["pending"] == 1
        assert data["counts"]["glossary"]["draft"] == 1
        assert ("pending" in data) == (actor == "admin")
        if actor == "admin":
            assert {draft["kind"] for draft in data["pending"]} == {"glossary", "buff"}
            assert all(draft["status"] == "pending" for draft in data["pending"])
