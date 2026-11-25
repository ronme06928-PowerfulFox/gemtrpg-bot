"""PR66-4 API visibility and persistent marks."""
from datetime import datetime, timezone
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from app import create_app
from extensions import db
from models import CatalogEncounter, CatalogEntry, User, Room, RoomMember
from manager.units import repository
from manager.catalog.kinds import inspect_payload, validate_payload
from manager.catalog.skills import from_cache, to_memory


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
                      "SQLALCHEMY_ENGINE_OPTIONS": {}}, run_startup=False, register_sockets=False)
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id="reader", name="reader"),
                            User(id="author", name="author", is_catalog_author=True),
                            User(id="admin", name="admin", is_app_admin=True)])
        for index, (visibility, marks, enemy) in enumerate([
            ("public", [], True), ("staff", [], True), ("staff", ["known"], True),
            ("public", ["known"], True), ("public", [], True),
            ("public", [], False), ("staff", [], True),
        ], 1):
            db.session.add(CatalogEntry(kind="unit", entry_id=f"U-{index:03}",
                visibility=visibility, payload={"name": f"unit{index}", "domain": "hollow" if index in (5, 7) else "session",
                                                "allow_enemy": enemy, "marks": marks}))
        db.session.add_all([CatalogEncounter(user_id="reader", kind="unit", entry_id="U-002",
                              first_seen_at=datetime(2026, 11, 18, tzinfo=timezone.utc), room_name="room"),
                           CatalogEncounter(user_id="author", kind="skill", entry_id="E-01",
                              first_seen_at=datetime(2026, 11, 17, tzinfo=timezone.utc), room_name="room")])
        db.session.add(CatalogEncounter(user_id="reader", kind="unit", entry_id="U-005",
                                       first_seen_at=datetime(2026, 11, 18, tzinfo=timezone.utc), room_name="room"))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def client(app, actor):
    result = app.test_client()
    if actor:
        with result.session_transaction() as session:
            session.update(user_id=actor, username=actor, auth_version=1)
    return result


@pytest.mark.parametrize('role,full', [('owner',True),('gm',True),('player',False),(None,False)])
def test_room_membership_visibility(app,role,full):
    room = Room(name='membership-room', data={})
    db.session.add(room)
    db.session.flush()
    if role:
        db.session.add(RoomMember(room_id=room.id,user_id='reader',role=role))
    db.session.commit()
    data=client(app,'reader').get('/api/encyclopedia?room=membership-room').json
    assert data['can_view_all'] is full
    assert data['can_preview_own'] is full
    ids={row['entry_id'] for row in data['units']}
    assert ('U-003' in ids) is full
    assert not {'U-005', 'U-007'} & ids
    assert 'U-005' not in {row['entry_id'] for row in data['encounters']}


@pytest.mark.parametrize("actor,visible,all_visible", [
    (None, [], False), ("reader", ["U-001", "U-002", "U-004"], False),
    ("author", ["U-001", "U-002", "U-003", "U-004", "U-005", "U-007"], True),
    ("admin", ["U-001", "U-002", "U-003", "U-004", "U-005", "U-007"], True),
])
def test_api_visibility_and_own_encounters(app, actor, visible, all_visible):
    response = client(app, actor).get("/api/encyclopedia")
    if actor is None:
        assert response.status_code == 401
        return
    assert response.status_code == 200
    data = response.json
    assert data["can_view_all"] is all_visible
    assert data["is_catalog_author"] is (actor == "author")
    assert [row["entry_id"] for row in data["units"]] == visible
    assert {row["entry_id"] for row in data["encounters"]} == (
        {"U-002"} if actor == "reader" else {"E-01"} if actor == "author" else set())
    assert all("room_name" not in row for row in data["encounters"])
    if actor == "reader":
        assert data["encounters"][0]["first_seen_at"].endswith("Z")


def test_known_survives_skill_and_unit_roundtrips(app):
    for kind, payload in [("buff", {"name": "known"}), ("item", {"name": "known"}),
                          ("passive", {"name": "known"}), ("skill", {"デフォルト名称": "known"})]:
        normalized = validate_payload(kind, payload | {"marks": ["known"]})
        assert normalized["marks"] == ["known"]
        assert any(p["field"] == "marks" for p in inspect_payload(
            kind, payload | {"marks": ["known", "known"]}, stage="submit"))
    skill = from_cache({"デフォルト名称": "known", "marks": ["known"]})
    assert to_memory(skill, "E-99")["marks"] == ["known"]
    row, _ = repository.save("unit", "U-001", {"name": "known", "domain": "session", "allow_enemy": True, "marks": ["known"]}, base_revision=1)
    assert repository.get("unit", row.entry_id).payload["marks"] == ["known"]
    assert repository.check("unit", {"name": "bad", "domain": "session", "marks": ["known", "known"]})[0]["marks"]
    assert repository.check("unit", {"name": "bad", "domain": "session", "marks": ["hollow"]})[0]["marks"]
    assert repository.check("unit", {"name": "bad", "domain": "session", "marks": "known"})[0]["marks"]


def test_non_enemy_skill_reference_does_not_warn(app):
    db.session.add(CatalogEntry(kind="skill", entry_id="Ps-99", payload={"デフォルト名称": "通常技"}))
    db.session.commit()
    problems = inspect_payload("item", {"name": "通常の道具", "effect": {"skill_id": "Ps-99"}}, stage="submit")
    assert not any("敵専用の" in problem["message"] for problem in problems)


def test_unit_without_allow_enemy_counts_as_enemy(app):
    db.session.add(CatalogEntry(kind="unit", entry_id="U-099", visibility="public", payload={"name": "old"}))
    db.session.commit()
    units = client(app, "reader").get("/api/encyclopedia").json["units"]
    assert "U-099" in [row["entry_id"] for row in units]


@pytest.mark.parametrize("actor,room,full",[("reader","room",False),("author","room",True),("reader","elsewhere",False),("reader","gm-room",True)])
def test_room_gm_can_view_all(app,actor,room,full,monkeypatch):
    import routes.encyclopedia as routes
    monkeypatch.setattr(routes,"resolve_room_role",lambda user, name:"gm" if user=="reader" and name=="gm-room" else "player" if name=="room" else None)
    data=client(app,actor).get("/api/encyclopedia",query_string={"room":room}).json
    assert data["can_view_all"] is full
    assert data["can_preview_own"] is full


def test_duplicate_session_unit_with_independent_patterns(app):
    author = client(app, "author")
    root = "/api/units"
    collection = author.post(root + "/unit_collection", json={"payload": {
        "name": "Session collection", "domain": "session",
    }}).json["entry"]
    source = author.post(root + "/unit", json={"visibility": "staff", "payload": {
        "name": "Original", "domain": "session", "collection_id": collection["entry_id"],
        "patterns": [{"id": "BP-1", "name": "Original pattern", "profile": {}}],
        "default_pattern_id": "BP-1",
    }}).json["entry"]
    path = f"{root}/unit/{source['entry_id']}"
    assert client(app, "reader").post(path + "/duplicate-to-hollow").status_code == 403
    response = author.post(path + "/duplicate-to-hollow")
    assert response.status_code == 201
    copy = response.json["entry"]
    assert copy["entry_id"] != source["entry_id"]
    assert copy["visibility"] == "staff"
    assert copy["payload"] == {**source["payload"], "domain": "hollow", "collection_id": None}
    source["payload"]["patterns"][0]["name"] = "Updated pattern"
    assert author.put(path, json={"payload": source["payload"], "base_revision": 1,
                                  "visibility": "staff"}).status_code == 200
    assert author.get(f"{root}/unit/{copy['entry_id']}").json == copy
    assert author.post(f"{root}/unit/{copy['entry_id']}/duplicate-to-hollow").status_code == 422
    assert copy["entry_id"] not in {row["entry_id"] for row in author.get(
        root + "?domain=session").json["entries"]}
    assert copy["entry_id"] in {row["entry_id"] for row in author.get(
        root + "?domain=hollow").json["entries"]}
