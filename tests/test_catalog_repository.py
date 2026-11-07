"""計画60 PR60-3: DBを正本とする用語と制作者。"""
import copy
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from app import create_app
from extensions import db, all_glossary_data
from models import User, CatalogEntry, CatalogDraft, CatalogHistory
from manager.catalog import repository as repo
from manager.catalog.kinds import validate_payload, CatalogValidationError
from manager.user_manager import is_catalog_author, set_catalog_author


@pytest.fixture
def catalog_app():
    app = create_app(config={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
                             "SQLALCHEMY_ENGINE_OPTIONS": {}},
                     run_startup=False, register_sockets=False)
    old = copy.deepcopy(all_glossary_data)
    with app.app_context():
        from sqlalchemy import text
        db.session.execute(text("PRAGMA foreign_keys = ON"))
        db.create_all()
        db.session.add_all([User(id="admin", name="Admin", is_app_admin=True),
                            User(id="author", name="Author"), User(id="reader", name="Reader")])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()
    all_glossary_data.clear()
    all_glossary_data.update(old)


def payload(**changes):
    return {"display_name": "用語", "category": "ルール", **changes}


@pytest.mark.parametrize("data,field", [({}, "display_name"),
    (payload(category="不明"), "category"), (payload(other=1), "other"),
    (payload(links=["W-99"]), "links"), (payload(links=["W-01"]), "links"),
    (payload(short=1), "short"), (payload(sort_order=True), "sort_order"),
    (payload(synonyms=[1]), "synonyms")])
def test_validation(data, field):
    with pytest.raises(CatalogValidationError) as exc:
        validate_payload("glossary", data, entry_id="W-01", published_ids={"W-01"})
    assert field in exc.value.errors


def test_draft_link_validation():
    validate_payload("glossary", payload(links=["X-1234abcd"]),
                     draft_ids={"X-1234abcd"})
    with pytest.raises(CatalogValidationError):
        validate_payload("glossary", payload(links=["X-1234abcd"]))


def test_seed_once_and_public_endpoint(catalog_app):
    reference = all_glossary_data
    assert repo.seed_kind_if_empty("glossary") == 83
    repo.load_kind_into_memory("glossary")
    assert all_glossary_data is reference and len(reference) == 83
    assert CatalogHistory.query.filter_by(action="import").count() == 83
    assert {e.revision for e in CatalogEntry.query.all()} == {1}
    assert repo.seed_kind_if_empty("glossary") == 0
    assert CatalogHistory.query.count() == 83
    assert "icon" not in reference["W-08"] and "is_enabled" not in reference["W-08"]
    reference.clear()
    assert len(catalog_app.test_client().get("/api/get_glossary_data").json) == 83


def test_draft_lifecycle_and_conflict(catalog_app):
    repo.seed_kind_if_empty("glossary")
    draft = repo.create_draft("glossary", "author", target_id="W-08")
    assert repo.create_draft("glossary", "reader", target_id="W-08").id == draft.id
    changed = {**draft.payload, "display_name": "改訂"}
    repo.update_draft(draft.id, changed)
    repo.submit_draft(draft.id)
    repo.reject_draft(draft.id, "理由")
    assert draft.status == "rejected" and draft.reject_reason == "理由"
    repo.update_draft(draft.id, changed)
    assert draft.status == "draft" and draft.reject_reason is None
    repo.submit_draft(draft.id)
    entry = repo.approve_draft(draft.id, "admin")
    assert entry.revision == 2 and all_glossary_data["W-08"]["display_name"] == "改訂"
    assert CatalogDraft.query.count() == 0
    assert CatalogHistory.query.filter_by(entry_id="W-08", revision=2).one().draft_id == draft.id
    stale = repo.create_draft("glossary", "author", target_id="W-08")
    repo.submit_draft(stale.id)
    repo.set_deprecated("glossary", "W-08", True, "admin")
    with pytest.raises(repo.CatalogConflictError):
        repo.approve_draft(stale.id, "admin")
    assert CatalogDraft.query.count() == 1
    assert all_glossary_data["W-08"]["deprecated"] is True
    restored = repo.restore_revision("glossary", "W-08", 1, "admin")
    assert restored.revision == 4 and restored.payload["display_name"] != "改訂"
    assert not all_glossary_data["W-08"]["deprecated"]
    repo.withdraw_draft(stale.id)
    assert CatalogDraft.query.count() == 0


def test_new_id_rewrites_other_drafts_atomically(catalog_app):
    first = repo.create_draft("glossary", "author")
    second = repo.create_draft("glossary", "author")
    repo.update_draft(first.id, payload())
    repo.update_draft(second.id, payload(links=[first.target_id]))
    repo.submit_draft(first.id)
    repo.submit_draft(second.id)
    with pytest.raises(CatalogValidationError):
        repo.approve_draft(second.id, "admin", entry_id="W-91")
    assert CatalogEntry.query.count() == 0 and second.status == "pending"
    for invalid in ("bad", second.target_id):
        with pytest.raises(CatalogValidationError):
            repo.approve_draft(first.id, "admin", entry_id=invalid)
    repo.approve_draft(first.id, "admin", entry_id="W-90")
    assert second.payload["links"] == ["W-90"]
    repo.approve_draft(second.id, "admin", entry_id="W-91")
    assert all_glossary_data["W-91"]["links"] == ["W-90"]
    duplicate = repo.create_draft("glossary", "author")
    repo.update_draft(duplicate.id, payload())
    repo.submit_draft(duplicate.id)
    with pytest.raises(repo.CatalogConflictError):
        repo.approve_draft(duplicate.id, "admin", entry_id="W-90")
    assert CatalogEntry.query.count() == 2


def test_author_permissions_and_account_response(catalog_app):
    assert is_catalog_author("admin") and not is_catalog_author("author")
    assert not is_catalog_author(None) and not set_catalog_author("missing", True)
    client = catalog_app.test_client()
    for actor, status in (("reader", 403), ("author", 403), ("admin", 200)):
        with client.session_transaction() as session:
            session.update(user_id=actor, username=actor, auth_version=1)
        response = client.post("/api/admin/set_catalog_author", json={"user_id": "author", "enabled": True})
        assert response.status_code == status
    assert is_catalog_author("author")
    assert next(u for u in client.get("/api/admin/users").json["users"] if u["id"] == "author")["is_catalog_author"]
    assert client.get("/api/get_session_user").json["is_catalog_author"]
    assert client.post("/api/admin/set_catalog_author", json={"user_id": "author", "enabled": "false"}).status_code == 400
    assert client.post("/api/admin/set_catalog_author", json={"user_id": "missing", "enabled": True}).status_code == 404
    assert client.post("/api/admin/set_catalog_author", json={"user_id": "author", "enabled": False}).status_code == 200
    assert not is_catalog_author("author")
    with client.session_transaction() as session:
        session.update(user_id="author", username="author", auth_version=1)
    assert client.get("/api/get_session_user").json["is_catalog_author"] is False



def test_failed_submission_leaves_draft_and_memory_unchanged(catalog_app):
    repo.seed_kind_if_empty("glossary")
    repo.load_kind_into_memory("glossary")
    before = copy.deepcopy(all_glossary_data)
    draft = repo.create_draft("glossary", "author")
    repo.update_draft(draft.id, payload(links=["W-9999"]))
    with pytest.raises(CatalogValidationError):
        repo.submit_draft(draft.id)
    assert draft.status == "draft" and draft.submitted_at is None
    assert all_glossary_data == before and CatalogHistory.query.count() == 83


def test_import_is_atomic_and_existing_db_never_reads_cache(catalog_app, monkeypatch):
    monkeypatch.setattr(repo, "load_json_cache", lambda _: {
        "W-01": payload(), "W-02": payload(links=["W-99"])})
    with pytest.raises(CatalogValidationError):
        repo.seed_kind_if_empty("glossary")
    assert CatalogEntry.query.count() == CatalogHistory.query.count() == 0
    monkeypatch.setattr(repo, "load_json_cache", lambda _: {"W-01": payload()})
    assert repo.seed_kind_if_empty("glossary") == 1
    monkeypatch.setattr(repo, "load_json_cache", lambda _: pytest.fail("既存DBでキャッシュを読まない"))
    db.session.remove()
    assert repo.seed_kind_if_empty("glossary") == 0
    repo.load_kind_into_memory("glossary")
    assert all_glossary_data["W-01"]["display_name"] == "用語"


def test_user_delete_keeps_catalog_and_nulls_attribution(catalog_app):
    from sqlalchemy import text
    draft = repo.create_draft("glossary", "author")
    repo.update_draft(draft.id, payload())
    repo.submit_draft(draft.id)
    repo.approve_draft(draft.id, "admin", entry_id="W-90")
    another = repo.create_draft("glossary", "author")
    db.session.execute(text("DELETE FROM users WHERE id IN ('author', 'admin')"))
    db.session.commit()
    db.session.expire_all()
    assert CatalogEntry.query.one().updated_by is None
    assert CatalogHistory.query.one().actor_user_id is None
    assert db.session.get(CatalogDraft, another.id).created_by is None


def test_admin_author_flag_migration(catalog_app):
    from sqlalchemy import text, inspect
    from manager.db_migration import run_auto_migration
    db.session.execute(text("ALTER TABLE users DROP COLUMN is_catalog_author"))
    db.session.commit()
    run_auto_migration(catalog_app)
    assert "is_catalog_author" in {c["name"] for c in inspect(db.engine).get_columns("users")}
    db.session.expire_all()
    assert not db.session.get(User, "reader").is_catalog_author
    assert is_catalog_author("admin")


def test_anonymous_cannot_assign_author(catalog_app):
    assert catalog_app.test_client().post("/api/admin/set_catalog_author",
        json={"user_id": "reader", "enabled": True}).status_code == 401



def test_new_id_rewrites_text_references_and_rejects_unresolved_text(catalog_app):
    first = repo.create_draft("glossary", "author")
    second = repo.create_draft("glossary", "author")
    unfinished = repo.create_draft("glossary", "author")
    repo.update_draft(first.id, payload())
    repo.update_draft(second.id, payload(long=f"[[{first.target_id}|参照先]]"))
    repo.update_draft(unfinished.id, {"short": first.target_id, "links": None})
    repo.submit_draft(first.id)
    repo.submit_draft(second.id)
    with pytest.raises(CatalogValidationError) as exc:
        repo.approve_draft(second.id, "admin", entry_id="W-91")
    assert "long" in exc.value.errors
    assert CatalogEntry.query.count() == 0
    repo.approve_draft(first.id, "admin", entry_id="W-90")
    assert second.payload["long"] == "[[W-90|参照先]]"
    assert unfinished.payload == {"short": "W-90", "links": None}
    repo.approve_draft(second.id, "admin", entry_id="W-91")
    assert all_glossary_data["W-91"]["long"] == "[[W-90|参照先]]"
