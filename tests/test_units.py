from flask import Flask
import pytest
from sqlalchemy import text, inspect

from extensions import db
from models import CatalogEntry
from manager.db_migration import run_auto_migration
from manager.units.characters import read_character, build_character
from manager.units import repository


@pytest.fixture
def unit_app(tmp_path):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'units.db'}"
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add(CatalogEntry(kind="skill", entry_id="E-23", payload={
            "デフォルト名称": "斬る", "チャットパレット": "2d6 【E-23 斬る】"
        }))
        db.session.commit()
        yield app
        db.session.remove()
        db.engine.dispose()


def test_character_json_and_runtime(unit_app):
    raw = {"kind": "character", "data": {
        "name": "敵", "characterType": "npc", "gmOnly": True,
        "status": [{"label": "HP", "value": 3, "max": 15}],
        "commands": "1d6 【E-23 固有名】\n1d100 【探索】", "memo": "discard",
        "SPassive": ["S-01", "Pa-02"], "radiance_skills": [{"id": "S-01"}],
        "special_buffs": [{"source": "radiance", "skill_id": "S-01"}],
        "flags": {"behavior_profile": {"enabled": True, "initial_loop_id": "a", "loops": {
            "a": {"steps": [{"actions": ["E-23"]}]}
        }}},
    }}
    unit, discarded = read_character(raw)
    assert unit["scenario"] and unit["gm_only"]
    assert unit["hp"] == 15
    assert unit["passives"] == ["Pa-02"] and unit["radiance"] == ["S-01"]
    assert discarded == ["memo"]
    assert unit["default_pattern_id"] == "BP-1"
    assert build_character(unit, "enemy", 1)["commands"] == "2d6 【E-23 固有名】\n1d100 【探索】"
    assert "behavior_profile" in build_character(unit, "enemy", 1)["flags"]
    assert "behavior_profile" not in build_character(unit, "ally", 1)["flags"]
    plain, discarded = read_character({"name": "味方", "isNPC": True, "color": "red"})
    assert plain["scenario"] and plain["patterns"] == []
    assert discarded == ["color"]
    assert read_character({"name": "クロウハンマー [敵 1]"})[0]["name"] == "クロウハンマー"


def test_direct_save_restore_and_references(unit_app):
    unit, _ = read_character({"name": "敵", "commands": "1d6 【E-23 斬る】"})
    row, _ = repository.save("unit", None, unit, visibility="staff")
    assert row.entry_id == "U-001"
    unit_id = row.entry_id
    formation = {"name": "敵編成", "type": "enemy",
                 "members": [{"unit_id": unit_id, "count": 1, "pattern_id": None}]}
    group, warnings = repository.save("formation", None, formation)
    assert len(warnings) == 2
    assert repository.entries(include_staff=False, include_deprecated=True).get(("unit", unit_id)) is None
    with pytest.raises(repository.CatalogConflictError):
        repository.save("unit", unit_id, unit, base_revision=0)
    repository.set_deprecated("unit", unit_id, True, base_revision=1)
    assert repository.get("unit", unit_id).deprecated
    assert repository.check("formation", formation, "public")[1]
    with pytest.raises(repository.CatalogConflictError):
        repository.delete("unit", unit_id, base_revision=2)
    restored, _ = repository.restore("unit", unit_id, 1, base_revision=2)
    assert restored.revision == 3 and not restored.deprecated and restored.visibility == "staff"
    assert [row.revision for row in repository.history("unit", unit_id)] == [3, 2, 1]
    formation["members"][0]["pattern_id"] = "missing"
    assert repository.check("formation", formation, "public")[0]
    unit["skills"] = [{"id": "missing"}]
    assert repository.check("unit", unit, "staff")[0]
    repository.delete("formation", group.entry_id, base_revision=1)
    repository.delete("unit", unit_id, base_revision=3)
    assert repository.get("unit", unit_id) is None


def test_legacy_tables_migrate_once(unit_app):
    db.session.execute(text("CREATE TABLE preset_resources ("
                            "id INTEGER PRIMARY KEY, resource_type TEXT, stable_id TEXT, name TEXT, "
                            "viewer_mode TEXT, payload JSON, collection_id TEXT, archived BOOLEAN)"))
    db.session.execute(text("CREATE TABLE preset_resource_acl (resource_id INTEGER "
                            "REFERENCES preset_resources(id))"))
    rows = [
        ("character", "old_u", '{"allow_enemy":true,"character_json":{"name":"敵"}}'),
        ("enemy_formation", "old_f", '{"members":[{"preset_id":"old_u","count":2}]}'),
        ("stage", "old_s", '{"enemy_formation_id":"old_f"}'),
        ("collection", "old_c", '{}'),
    ]
    for kind, key, payload in rows:
        db.session.execute(text("INSERT INTO preset_resources "
                                "(resource_type,stable_id,name,viewer_mode,payload,collection_id,archived) "
                                "VALUES (:kind,:key,:key,'restricted',:payload,'old_c',false)"),
                           {"kind": kind, "key": key, "payload": payload})
    from models import Room

    db.session.add(Room(name="saved-room", data={"battle_only": {
        "selected_stage_id": "old_s", "enemy_formation_id": "old_f",
        "enemy_entries": [{"preset_id": "old_u", "count": 2, "behavior_profile_override": {}}],
    }}))
    db.session.commit()
    run_auto_migration(unit_app)
    run_auto_migration(unit_app)
    draft = Room.query.filter_by(name="saved-room").one().data["battle_only"]
    assert draft["selected_stage_id"] == "ST-001"
    assert draft["enemy_formation_id"] == "F-001"
    assert draft["enemy_entries"] == [{"preset_id": "U-001", "count": 2}]
    with pytest.raises(repository.CatalogConflictError):
        repository.delete("stage", "ST-001", base_revision=1)
    assert repository.get("unit", "U-001").visibility == "staff"
    assert repository.get("formation", "F-001").payload["members"] == [
        {"unit_id": "U-001", "count": 2, "pattern_id": None}
    ]
    assert repository.get("stage", "ST-001").payload["enemy_formation_id"] == "F-001"
    assert len(repository.entries()) == 4
    assert not {"preset_resources", "preset_resource_acl"} & set(inspect(db.engine).get_table_names())


def test_legacy_migration_drops_dangling_references(unit_app):
    db.session.execute(text("CREATE TABLE preset_resources ("
                            "id INTEGER PRIMARY KEY, resource_type TEXT, stable_id TEXT, name TEXT, "
                            "viewer_mode TEXT, payload JSON, collection_id TEXT, archived BOOLEAN)"))
    rows = [
        ("character", "old_u", '{"character_json":{"name":"敵"}}', None),
        ("enemy_formation", "old_f", '{"members":[{"preset_id":"old_u"},{"preset_id":"gone"}]}', "gone_c"),
        ("stage", "old_s", '{"enemy_formation_id":"gone_f","ally_formation_id":"old_f"}', None),
    ]
    for kind, key, payload, collection in rows:
        db.session.execute(text("INSERT INTO preset_resources "
                                "(resource_type,stable_id,name,viewer_mode,payload,collection_id,archived) "
                                "VALUES (:kind,:key,:key,'public',:payload,:collection,false)"),
                           {"kind": kind, "key": key, "payload": payload, "collection": collection})
    db.session.commit()
    run_auto_migration(unit_app)
    formation = repository.get("formation", "F-001").payload
    assert formation["members"] == [{"unit_id": "U-001", "count": 1, "pattern_id": None}]
    assert formation["collection_id"] is None
    stage = repository.get("stage", "ST-001").payload
    assert stage["enemy_formation_id"] is None


def test_http_permissions_and_package_preview_confirm(unit_app):
    from models import Room, RoomMember, User
    from routes.units import units_bp

    unit_app.secret_key = "unit-test"
    unit_app.register_blueprint(units_bp)
    db.session.add_all([
        User(id="author", name="author", is_catalog_author=True),
        User(id="admin", name="admin", is_app_admin=True),
        User(id="gm", name="gm"),
        User(id="reader", name="reader"),
        Room(name="room-a"), Room(name="room-b"),
    ])
    db.session.flush()
    db.session.add(RoomMember(room_id=Room.query.filter_by(name="room-a").one().id,
                              user_id="gm", role="gm"))
    db.session.commit()

    def client(user):
        connection = unit_app.test_client()
        with connection.session_transaction() as session:
            session.update(user_id=user, username=user, auth_version=1)
        return connection

    author, admin, gm, reader = map(client, ("author", "admin", "gm", "reader"))
    root = "/api/units"
    imported = author.post(root + "/import-character", json={"character": {
        "character_json": {"name": "Staff", "memo": "discard", "commands": "1d6 【E-23 斬る】"},
        "allow_ally": False,
    }})
    assert imported.json["discarded"] == ["memo"]
    assert imported.json["errors"] == {}
    assert not imported.json["payload"]["allow_ally"]
    unit = author.post(root + "/unit", json={"payload": imported.json["payload"], "visibility": "staff"})
    assert unit.status_code == 201
    assert unit.json["entry"]["entry_id"] == "U-001"
    col = admin.post(root + "/unit_collection", json={"payload": {"name": "分類"}})
    assert col.status_code == 201
    formation = author.post(root + "/formation", json={"payload": {
        "name": "Public", "type": "enemy", "collection_id": "SC-01",
        "members": [{"unit_id": "U-001", "count": 2, "pattern_id": None}],
    }})
    assert formation.status_code == 201
    assert len(formation.json["warnings"]) == 2
    path = root + "/unit/U-001"
    assert author.get(path).status_code == 200
    assert admin.get(path).status_code == 200
    assert gm.get(path + "?room=room-a").status_code == 200
    assert gm.get(path + "?room=room-b").status_code == 404
    assert gm.get(path).status_code == 404
    assert reader.get(path + "?room=room-a").status_code == 404
    assert reader.get(path + "/history").status_code == 404
    assert reader.get(root + "/unit").json["entries"] == []
    assert gm.put(path + "?room=room-a", json={}).status_code == 403
    assert gm.get(root + "/export?room=room-a").status_code == 403

    package = author.get(root + "/export?collection_id=SC-01").json
    assert {row["entry_id"] for row in package["entries"]} == {"U-001", "F-001", "SC-01"}
    assert all("revision" not in row for row in package["entries"])
    package["entries"].append({"kind": "stage", "entry_id": "ST-001", "visibility": "staff",
                               "deprecated": False, "payload": {"name": "Stage", "enemy_formation_id": "F-001"}})
    preview_path, confirm_path = root + "/import/preview", root + "/import/confirm"
    report = author.post(preview_path, json={"package": package}).json["entries"]
    assert {row["operation"] for row in report} == {"new", "overwrite"}
    assert all(not row["errors"] for row in report)
    revisions = {f"{row['kind']}:{row['entry_id']}": row["base_revision"] for row in report}
    assert repository.get("stage", "ST-001") is None

    author.put(path, json={"payload": imported.json["payload"], "base_revision": 1, "visibility": "staff"})
    assert author.post(confirm_path, json={"package": package, "base_revisions": revisions}).status_code == 409
    assert repository.get("stage", "ST-001") is None
    revisions["unit:U-001"] = 2
    broken = next(row for row in package["entries"] if row["kind"] == "stage")
    broken["payload"]["enemy_formation_id"] = "F-999"
    assert author.post(confirm_path, json={"package": package, "base_revisions": revisions}).status_code == 422
    assert repository.get("unit", "U-001").revision == 2
    broken["payload"]["enemy_formation_id"] = "F-001"
    response = author.post(confirm_path, json={"package": package, "base_revisions": revisions})
    assert response.status_code == 200
    assert repository.get("unit", "U-001").revision == 3
    assert repository.get("stage", "ST-001").revision == 1


def test_validation_of_default_patterns_sides_and_master_deprecation(unit_app):
    unit, _ = read_character({"name": "敵", "commands": "1d6 【E-23 斬る】"})
    unit["patterns"] = [{"id": "BP-a", "name": "A", "profile": {
        "initial_loop_id": "start", "loops": {"start": {"steps": [{"actions": ["E-99"]}]}},
    }}]
    assert "patterns[0]" in repository.check("unit", unit)[0]
    unit["patterns"][0]["profile"]["loops"]["start"]["steps"][0]["actions"] = ["E-23"]
    unit["allow_ally"] = False
    saved, _ = repository.save("unit", None, unit)
    assert saved.payload["default_pattern_id"] == "BP-a"
    unit["patterns"].append({"id": "BP-b", "name": "B", "profile": {}})
    assert "default_pattern_id" in repository.check("unit", unit, entry_id=saved.entry_id)[0]
    formation = {"name": "味方", "type": "ally", "members": [{
        "unit_id": saved.entry_id, "count": 1, "pattern_id": "BP-missing",
    }]}
    assert set(repository.check("formation", formation)[0]) == {
        "members[0].unit_id", "members[0].pattern_id",
    }
    master = CatalogEntry.query.filter_by(kind="skill", entry_id="E-23").one()
    master.deprecated = True
    db.session.commit()
    assert "skills[0]" in repository.check("unit", unit | {"default_pattern_id": "BP-a"})[0]


def test_catalog_units_build_normal_battle_draft_and_simulator(unit_app):
    from manager.preset_deployment import apply_deployment
    from manager.sim.preset_loader import build_room_state_from_presets
    from manager.units.runtime import deployment_store

    unit, _ = read_character({"name": "Test", "commands": "1d6 【E-23 固有名】"})
    unit["patterns"] = [
        {"id": "BP-1", "name": "usual", "profile": {"enabled": False}},
        {"id": "BP-2", "name": "alternate", "profile": {"enabled": True,
            "initial_loop_id": "start", "loops": {"start": {"steps": [{"actions": ["E-23"]}]}}}},
    ]
    unit["default_pattern_id"] = "BP-1"
    repository.save("unit", None, unit)
    for side in ("ally", "enemy"):
        repository.save("formation", None, {"name": side, "type": side, "members": [
            {"unit_id": "U-001", "count": 1, "pattern_id": "BP-2"},
        ]})
    repository.save("stage", None, {"name": "Stage", "enemy_formation_id": "F-002",
                                   "ally_formation_id": "F-001"})
    store = deployment_store()
    for mode in ("normal", "battle_only"):
        state = {"play_mode": mode, "characters": [], "character_owners": {}}
        summary, _ = apply_deployment(state, {"target_mode": mode, "stage": {
            "record_id": "ST-001", "apply": {"ally_formation": True},
        }},
                                      store, room_role="gm", gm_user={"user_id": "gm", "username": "GM"},
                                      active_users={"gm": "GM"})
        assert summary["added"] == {"ally": 1, "enemy": 1}
        if mode == "normal":
            ally, enemy = state["characters"]
            assert "behavior_profile" not in ally["flags"]
            assert enemy["flags"]["behavior_profile"]["enabled"]
            assert enemy["commands"] == "2d6 【E-23 固有名】"
        else:
            assert state["battle_only"]["enemy_entries"][0]["pattern_id"] == "BP-2"
    sim = build_room_state_from_presets(stage_id="ST-001")
    ally, enemy = sim["characters"]
    assert "behavior_profile" not in ally["flags"]
    assert enemy["flags"]["behavior_profile"]["enabled"]
    assert enemy["commands"] == "2d6 【E-23 固有名】"


def test_export_deprecated_filter_keeps_dependencies(unit_app):
    from manager.units import transfer

    used, _ = repository.save("unit", None, {"name": "Used"})
    unused, _ = repository.save("unit", None, {"name": "Unused"})
    formation, _ = repository.save("formation", None, {"name": "Enemy", "type": "enemy",
        "members": [{"unit_id": used.entry_id, "count": 1}]})
    for row in (used, unused):
        repository.set_deprecated("unit", row.entry_id, True, base_revision=1)
    assert {row["entry_id"] for row in transfer.export_package(include_deprecated=False)["entries"]} == {
        used.entry_id, formation.entry_id,
    }
    assert len(transfer.export_package(include_deprecated=True)["entries"]) == 3


def test_formation_side_is_immutable_after_create(unit_app):
    from manager.units import transfer

    payload = {"name": "Enemy", "type": "enemy", "members": []}
    row, _ = repository.save("formation", None, payload)
    updated = {**payload, "type": "ally"}
    assert "type" in repository.check("formation", updated, entry_id=row.entry_id)[0]
    with pytest.raises(repository.CatalogValidationError):
        repository.save("formation", row.entry_id, updated, base_revision=1)
    package = transfer.export_package()
    package["entries"][0]["payload"] = updated
    assert "type" in transfer.preview(package)[0]["errors"]


def test_initial_states_are_discarded_and_start_at_zero(unit_app):
    unit, discarded = read_character({"name": "Enemy", "states": {"FP": 8}, "status": [
        {"label": "HP", "value": 8, "max": 12},
        {"label": "MP", "value": 2, "max": 6},
        {"label": "出血", "value": 10},
        {"name": "FP", "value": 5},
    ]})
    assert discarded == ["states", "status.出血", "status.FP"]
    assert "states" not in unit
    incoming = {**unit, "states": {"FP": 8, "custom": 4}}
    saved, _ = repository.save("unit", None, incoming)
    assert "states" not in saved.payload
    for side in ("enemy", "ally"):
        char = build_character(incoming, side, 1)
        assert char["hp"] == 8 and char["mp"] == 2
        assert not any(row["value"] or row["name"] == "custom" for row in char["states"])
        assert all(row["value"] == 0 for row in char["initial_status"][2:])


def test_startup_removes_initial_states_from_units_and_history(unit_app):
    from models import CatalogHistory

    row, _ = repository.save("unit", None, {"name": "Enemy", "hp": 9, "initial_hp": 4})
    key = row.entry_id
    for old in (row, CatalogHistory.query.filter_by(kind="unit", entry_id=key).one()):
        old.payload = {**old.payload, "states": {"FP": 7}}
    db.session.commit()

    for _ in range(2):
        run_auto_migration(unit_app)
        db.session.expire_all()
        current = repository.get("unit", key)
        assert current.revision == 1
        assert current.payload == {"name": "Enemy", "hp": 9, "initial_hp": 4}
        assert [snapshot.payload for snapshot in repository.history("unit", key)] == [current.payload]


def test_formation_saves_cloned_pattern_and_member_atomically(unit_app):
    profile = {"enabled": True, "loops": {"a": {"steps": [{"actions": ["E-23"]}]}}}
    unit, _ = repository.save("unit", None, {"name": "Enemy", "skills": [{"id": "E-23"}],
        "patterns": [{"id": "BP-1", "name": "First", "profile": profile}]})
    unit_id = unit.entry_id
    pattern = {"id": "BP-2", "name": "Second", "profile": profile}
    additions = {unit_id: {"base_revision": 1, "patterns": [pattern]}}
    members = [{"unit_id": unit_id, "count": 1, "pattern_id": "BP-2"}]
    formation = {"name": "Enemy group", "type": "enemy", "members": members}
    assert not repository.check("formation", formation, pattern_additions=additions)[0]
    with pytest.raises(repository.CatalogValidationError):
        repository.save("formation", None, {**formation, "name": ""}, pattern_additions=additions)
    assert repository.get("unit", unit_id).revision == 1
    row, _ = repository.save("formation", None, formation, pattern_additions=additions)
    assert row.payload["members"][0]["pattern_id"] == "BP-2"
    saved_unit = repository.get("unit", unit_id)
    assert saved_unit.revision == 2
    assert saved_unit.payload["default_pattern_id"] == "BP-1"
    assert build_character(saved_unit.payload, "enemy", 1, pattern_id="BP-2")["flags"]["behavior_profile"]["enabled"]
    assert repository.check("unit", {**saved_unit.payload, "patterns": saved_unit.payload["patterns"][:1]},
                            entry_id=unit_id)[0]
    with pytest.raises(repository.CatalogConflictError):
        repository.save("formation", None, formation, pattern_additions=additions)


def test_deploying_saved_stage_normalizes_skill_constraints(unit_app):
    from manager.preset_deployment import apply_deployment
    from manager.units.runtime import deployment_store

    stage, _ = repository.save("stage", None, {
        "name": "制約を持つステージ",
        "field_effect_profile": {"version": 1, "rules": [{
            "rule_id": "limit",
            "type": "SPEED_ROLL_MOD",
            "scope": "ALL",
            "value": -1,
            "skill_constraints": {"mode": "block", "match": {"skill_id": "E-23"}},
        }]},
    })
    state = {"characters": []}
    apply_deployment(state, {"stage": {"id": stage.entry_id}}, deployment_store(), room_role="gm")

    rules = state["stage_field_effect_profile"]["rules"]
    assert len(rules) == 1
    assert rules[0]["skill_constraints"][0]["mode"] == "block"
    assert rules[0]["skill_constraints"][0]["match"]["skill_id"] == "E-23"
    assert state["field_effects"][0]["source_id"] == stage.entry_id
