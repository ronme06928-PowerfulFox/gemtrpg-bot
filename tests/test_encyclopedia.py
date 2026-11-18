"""PR66-4 API visibility and persistent marks."""
from datetime import datetime, timezone
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from app import create_app
from extensions import db
from models import CatalogEncounter, CatalogEntry, User
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
            ("public", ["known"], True), ("public", ["hollow"], True),
            ("public", [], False), ("staff", ["hollow"], True),
        ], 1):
            db.session.add(CatalogEntry(kind="unit", entry_id=f"U-{index:03}",
                visibility=visibility, payload={"name": f"unit{index}", "allow_enemy": enemy, "marks": marks}))
        db.session.add_all([CatalogEncounter(user_id="reader", kind="unit", entry_id="U-002",
                              first_seen_at=datetime(2026, 11, 18, tzinfo=timezone.utc), room_name="room"),
                           CatalogEncounter(user_id="author", kind="skill", entry_id="E-01",
                              first_seen_at=datetime(2026, 11, 17, tzinfo=timezone.utc), room_name="room")])
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
    skill = from_cache({"デフォルト名称": "known", "marks": ["known", "hollow"]})
    assert to_memory(skill, "E-99")["marks"] == ["known", "hollow"]
    row, _ = repository.save("unit", "U-001", {"name": "known", "allow_enemy": True, "marks": ["known"]}, base_revision=1)
    assert repository.get("unit", row.entry_id).payload["marks"] == ["known"]
    assert repository.check("unit", {"name": "bad", "marks": ["known", "known"]})[0]["marks"]
    assert repository.check("unit", {"name": "bad", "marks": ["unknown"]})[0]["marks"]
    assert repository.check("unit", {"name": "bad", "marks": "known"})[0]["marks"]


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
