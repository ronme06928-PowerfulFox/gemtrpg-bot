import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db
from manager.battle_only_presets import load_store, mutate_store
from manager.preset_transfer import (
    PresetPackageError,
    apply_package,
    build_collection_package,
    parse_package,
    preview_package,
)
from manager.user_manager import delete_user, transfer_ownership
from models import PresetResource, PresetResourceAcl, User


@pytest.fixture
def app_ctx(tmp_path):
    app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'presets.db').as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    with app.app_context():
        db.create_all()
        db.session.add_all([
            User(id="owner", name="Owner"),
            User(id="other", name="Other"),
            User(id="viewer", name="Viewer"),
        ])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _acl(owner="owner", mode="restricted"):
    return {
        "owner_user_id": owner,
        "editor_user_ids": [],
        "viewer_mode": mode,
        "viewer_user_ids": [],
    }


def _meta(collection_id="scenario_02", section_id="boss"):
    return {
        "collection_id": collection_id,
        "section_id": section_id,
        "sort_order": 10,
        "labels": ["scenario02"],
        "archived": False,
        "last_used_at": 0,
    }


def _populate_store():
    def mutate(store):
        store["catalog_collections"]["scenario_02"] = {
            "id": "scenario_02",
            "name": "シナリオ2",
            "description": "移送テスト",
            "sections": [{"id": "boss", "name": "ボス戦", "sort_order": 1}],
            "access_control": _acl(),
            "visibility": "restricted",
        }
        store["character_presets"]["iron_root"] = {
            "id": "iron_root",
            "name": "アイアンルート",
            "character_json": {"kind": "character", "data": {"name": "アイアンルート"}},
            "access_control": _acl(),
            "visibility": "restricted",
            "catalog_meta": _meta(),
        }
        store["enemy_formations"]["boss_team"] = {
            "id": "boss_team",
            "name": "ボス編成",
            "members": [{"preset_id": "iron_root", "count": 1}],
            "access_control": _acl(),
            "visibility": "restricted",
            "catalog_meta": _meta(),
        }
        store["stage_presets"]["boss_stage"] = {
            "id": "boss_stage",
            "name": "ボス戦",
            "enemy_formation_id": "boss_team",
            "ally_formation_id": None,
            "access_control": _acl(),
            "visibility": "restricted",
            "catalog_meta": _meta(),
        }

    mutate_store(mutate)


def test_empty_db_does_not_automatically_import_legacy_json(app_ctx):
    store = load_store()
    assert store["character_presets"] == {}
    assert store["catalog_collections"] == {}


def test_resource_store_round_trip_and_last_used_does_not_increment_revision(app_ctx):
    _populate_store()
    store = load_store()
    assert store["stage_presets"]["boss_stage"]["enemy_formation_id"] == "boss_team"
    assert PresetResource.query.count() == 4
    assert PresetResourceAcl.query.count() == 0

    before = store["character_presets"]["iron_root"]["revision"]
    mutate_store(lambda current: current["character_presets"]["iron_root"]["catalog_meta"].update({"last_used_at": 1234}))
    after_touch = load_store()["character_presets"]["iron_root"]
    assert after_touch["revision"] == before
    assert after_touch["catalog_meta"]["last_used_at"] == 1234

    mutate_store(lambda current: current["character_presets"]["iron_root"].update({"name": "アイアンルート改"}))
    after_edit = load_store()["character_presets"]["iron_root"]
    assert after_edit["revision"] == before + 1
    assert after_edit["name"] == "アイアンルート改"


def test_acl_rows_round_trip_and_user_transfer_are_atomic(app_ctx):
    _populate_store()

    def share(store):
        acl = store["character_presets"]["iron_root"]["access_control"]
        acl["editor_user_ids"] = ["other"]
        acl["viewer_user_ids"] = ["viewer"]

    mutate_store(share)
    assert PresetResourceAcl.query.count() == 2
    shared = load_store()["character_presets"]["iron_root"]["access_control"]
    assert shared["editor_user_ids"] == ["other"]
    assert shared["viewer_user_ids"] == ["viewer"]

    result = transfer_ownership("owner", "other")
    assert result["preset_assets"]["total"] == 4
    transferred = load_store()
    for map_key in (
        "character_presets",
        "enemy_formations",
        "stage_presets",
        "catalog_collections",
    ):
        for record in transferred[map_key].values():
            assert record["access_control"]["owner_user_id"] == "other"
            assert "owner" not in record["access_control"]["editor_user_ids"]
            assert "owner" not in record["access_control"]["viewer_user_ids"]

    assert delete_user("owner") is True
    assert db.session.get(User, "owner") is None


def test_collection_package_import_and_copy_remap_references(app_ctx):
    _populate_store()
    source = load_store()
    package = build_collection_package(source, "scenario_02", can_view=lambda _kind, _record: True)
    assert len(package["resources"]) == 4

    def clear(store):
        for key in (
            "character_presets",
            "enemy_formations",
            "ally_formations",
            "stage_presets",
            "catalog_collections",
        ):
            store[key].clear()

    mutate_store(clear)
    empty = load_store()
    preview = preview_package(
        package,
        empty,
        can_update=lambda _kind, _record: False,
        can_use_existing=lambda _kind, _record: False,
    )
    assert preview["can_import"] is True
    assert preview["counts"] == {"new": 4, "conflict": 0}

    result = {}
    mutate_store(lambda store: result.update(apply_package(
        package,
        store,
        owner_user_id="owner",
        owner_name="Owner",
        actions={},
        can_update=lambda _kind, _record: True,
        can_use_existing=lambda _kind, _record: True,
    )))
    assert len(result["created"]) == 4
    imported = load_store()
    assert imported["character_presets"]["iron_root"]["access_control"] == _acl()

    conflict_preview = preview_package(
        package,
        imported,
        can_update=lambda _kind, _record: True,
        can_use_existing=lambda _kind, _record: True,
    )
    copy_actions = {item["key"]: "copy" for item in conflict_preview["items"]}
    copy_result = {}
    mutate_store(lambda store: copy_result.update(apply_package(
        package,
        store,
        owner_user_id="other",
        owner_name="Other",
        actions=copy_actions,
        can_update=lambda _kind, _record: False,
        can_use_existing=lambda _kind, _record: True,
    )))
    copied_stage_id = copy_result["id_map"]["stage:boss_stage"]
    copied_formation_id = copy_result["id_map"]["enemy_formation:boss_team"]
    copied_character_id = copy_result["id_map"]["character:iron_root"]
    copied = load_store()
    assert copied["stage_presets"][copied_stage_id]["enemy_formation_id"] == copied_formation_id
    assert copied["enemy_formations"][copied_formation_id]["members"][0]["preset_id"] == copied_character_id
    assert copied["character_presets"][copied_character_id]["access_control"]["owner_user_id"] == "other"


def test_package_update_detects_revision_conflict_without_partial_commit(app_ctx):
    _populate_store()
    original = load_store()
    package = build_collection_package(original, "scenario_02", can_view=lambda _kind, _record: True)
    preview = preview_package(
        package,
        original,
        can_update=lambda _kind, _record: True,
        can_use_existing=lambda _kind, _record: True,
    )
    expected_revisions = {
        item["key"]: item["existing_revision"]
        for item in preview["items"]
        if item["existing_revision"] is not None
    }
    actions = {item["key"]: "update" for item in preview["items"]}
    mutate_store(lambda store: store["character_presets"]["iron_root"].update({"name": "先行更新"}))

    with pytest.raises(PresetPackageError, match="character:iron_root"):
        mutate_store(lambda store: apply_package(
            package,
            store,
            owner_user_id="owner",
            owner_name="Owner",
            actions=actions,
            expected_revisions=expected_revisions,
            can_update=lambda _kind, _record: True,
            can_use_existing=lambda _kind, _record: True,
        ))

    current = load_store()
    assert current["character_presets"]["iron_root"]["name"] == "先行更新"
    assert current["catalog_collections"]["scenario_02"]["name"] == "シナリオ2"


def test_package_rejects_invalid_source_revision(app_ctx):
    package = {
        "schema": "gem_dicebot_preset_package.v1",
        "schema_version": 1,
        "resources": [{
            "resource_type": "character",
            "stable_id": "invalid_revision",
            "source_revision": "not-a-number",
            "record": {"name": "invalid"},
        }],
    }
    with pytest.raises(PresetPackageError) as exc_info:
        parse_package(package)
    assert exc_info.value.code == "invalid_resource"
