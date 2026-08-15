from types import SimpleNamespace

from events.battle_only import catalog_v3_routes
from manager.battle_only_catalog_access import (
    capabilities,
    clear_collection_references,
    owned_asset_counts,
    normalize_record_security,
    reference_blockers,
    reference_scope_covers,
    sanitize_record_for_user,
    inspect_deploy_references,
    touch_last_used_for_battle,
    transfer_user_assets,
    validate_parent_references,
)
from manager.battle_only_presets import _normalize_store
from manager.room_manager import build_participant_state


def _record(record_id, mode="public", owner="owner", **extra):
    record = {
        "id": record_id,
        "name": record_id,
        "visibility": mode,
        "access_control": {
            "owner_user_id": owner,
            "editor_user_ids": ["editor"],
            "viewer_mode": mode,
            "viewer_user_ids": ["viewer"],
        },
        "catalog_meta": {
            "collection_id": None,
            "section_id": None,
            "labels": [],
            "sort_order": 10,
            "archived": False,
            "last_used_at": 0,
        },
    }
    record.update(extra)
    return record


def test_v2_store_is_normalized_to_v3_without_losing_records():
    store = _normalize_store({
        "version": 2,
        "presets": {
            "legacy": {
                "id": "legacy",
                "name": "Legacy",
                "visibility": "gm",
                "character_json": {"name": "Legacy"},
            },
        },
    })

    assert store["version"] == 3
    assert store["catalog_collections"] == {}
    record = store["character_presets"]["legacy"]
    assert record["character_json"]["name"] == "Legacy"
    assert record["access_control"]["owner_user_id"] is None
    assert record["access_control"]["viewer_mode"] == "gm"


def test_capabilities_distinguish_owner_editor_viewer_gm_and_admin():
    record = _record("restricted", mode="restricted")

    assert capabilities(record, user_id="owner")["can_manage_acl"] is True
    assert capabilities(record, user_id="editor")["can_edit"] is True
    assert capabilities(record, user_id="editor")["can_manage_acl"] is False
    assert capabilities(record, user_id="viewer")["can_view"] is True
    assert capabilities(record, user_id="viewer")["can_edit"] is False
    assert capabilities(record, user_id="stranger")["can_view"] is False
    assert capabilities(record, user_id="stranger", is_app_admin=True)["can_delete"] is True

    gm_record = _record("gm", mode="gm")
    assert capabilities(gm_record, user_id="stranger")["can_view"] is False
    gm_caps = capabilities(gm_record, user_id="stranger", room_role="gm")
    assert gm_caps["can_view"] is True
    assert gm_caps["can_deploy"] is True
    assert gm_caps["can_edit"] is False


def test_acl_members_are_hidden_from_non_owner_responses():
    viewer = sanitize_record_for_user(_record("p"), user_id="viewer")
    owner = sanitize_record_for_user(_record("p"), user_id="owner")

    assert "access_control" not in viewer
    assert owner["access_control"]["viewer_user_ids"] == ["viewer"]


def test_new_record_owner_cannot_be_spoofed_and_editor_cannot_replace_acl():
    created = normalize_record_security(
        {
            "visibility": "restricted",
            "access_control": {
                "owner_user_id": "spoofed",
                "editor_user_ids": ["attacker"],
                "viewer_mode": "restricted",
                "viewer_user_ids": [],
            },
        },
        creator_user_id="creator",
        allow_acl=True,
    )
    assert created["access_control"]["owner_user_id"] == "creator"

    existing = _record("record")
    edited = normalize_record_security(
        {"access_control": {"owner_user_id": "attacker"}},
        creator_user_id="editor",
        existing=existing,
        allow_acl=False,
    )
    assert edited["access_control"] == existing["access_control"]


def test_reference_scope_rejects_public_parent_with_private_child():
    public_parent = _record("formation", mode="public")
    private_child = _record("character", mode="restricted")
    assert reference_scope_covers(public_parent, private_child) is False

    private_parent = _record("formation", mode="restricted")
    assert reference_scope_covers(private_parent, private_child) is True


def test_reference_validation_and_delete_blockers_cover_full_chain():
    store = {
        "character_presets": {"char": _record("char")},
        "enemy_formations": {
            "formation": _record("formation", members=[{"preset_id": "char", "count": 1}]),
        },
        "ally_formations": {},
        "stage_presets": {
            "stage": _record("stage", enemy_formation_id="formation", ally_formation_id=None),
        },
        "catalog_collections": {},
    }

    assert validate_parent_references(store, "enemy_formation", store["enemy_formations"]["formation"])
    assert validate_parent_references(store, "stage", store["stage_presets"]["stage"])
    assert reference_blockers(store, "character", "char")[0]["id"] == "formation"
    assert reference_blockers(store, "enemy_formation", "formation")[0]["id"] == "stage"


def test_deploy_reference_inspection_reports_missing_record_details():
    store = {
        "character_presets": {"char": _record("char")},
        "enemy_formations": {},
        "ally_formations": {},
        "stage_presets": {},
        "catalog_collections": {},
    }
    result = inspect_deploy_references(
        store,
        {
            "selected_stage_id": "missing_stage",
            "enemy_entries": [{"preset_id": "missing_enemy"}],
        },
        user_id="owner",
        room_role="gm",
    )

    assert result["valid"] is False
    assert {(row["record_type"], row["record_id"], row["reason"]) for row in result["failures"]} == {
        ("stage", "missing_stage", "missing"),
        ("character", "missing_enemy", "missing"),
    }
    assert all("存在しません" in row["message"] for row in result["failures"])


def test_deploy_reference_inspection_ignores_optional_none_values():
    result = inspect_deploy_references(
        {
            "character_presets": {"enemy": _record("enemy")},
            "enemy_formations": {},
            "ally_formations": {},
            "stage_presets": {},
        },
        {
            "selected_stage_id": "None",
            "enemy_formation_id": None,
            "ally_formation_id": "null",
            "enemy_entries": [{"preset_id": "enemy"}],
        },
        user_id="owner",
        room_role="gm",
    )

    assert result == {"valid": True, "failures": []}


def test_collection_removal_unclassifies_records_without_deleting_them():
    record = _record("char")
    record["catalog_meta"].update({"collection_id": "scenario_2", "section_id": "battle_1"})
    store = {
        "character_presets": {"char": record},
        "enemy_formations": {},
        "ally_formations": {},
        "stage_presets": {},
        "catalog_collections": {},
    }

    assert clear_collection_references(store, "scenario_2", section_id="battle_1") == 1
    assert store["character_presets"]["char"]["catalog_meta"]["collection_id"] == "scenario_2"
    assert store["character_presets"]["char"]["catalog_meta"]["section_id"] is None
    assert clear_collection_references(store, "scenario_2") == 1
    assert store["character_presets"]["char"]["catalog_meta"]["collection_id"] is None


def test_bulk_ownership_transfer_covers_all_asset_types():
    store = {
        "character_presets": {"char": _record("char", owner="old")},
        "enemy_formations": {"enemy": _record("enemy", owner="old")},
        "ally_formations": {"ally": _record("ally", owner="old")},
        "stage_presets": {"stage": _record("stage", owner="old")},
        "catalog_collections": {"collection": _record("collection", owner="old")},
    }

    assert owned_asset_counts(store, "old")["total"] == 5
    result = transfer_user_assets(store, "old", "new")
    assert result["total"] == 5
    assert owned_asset_counts(store, "new")["total"] == 5


def test_last_used_and_participant_state_do_not_leak_management_metadata():
    record = _record("stage", updated_at=123)
    store = {
        "character_presets": {},
        "enemy_formations": {},
        "ally_formations": {},
        "stage_presets": {"stage": record},
        "catalog_collections": {},
    }
    battle_only = {"selected_stage_id": "stage", "preset_bookmarks": [{"id": "bookmark"}]}

    assert touch_last_used_for_battle(store, battle_only, 999) == 1
    assert record["catalog_meta"]["last_used_at"] == 999
    assert record["updated_at"] == 123

    public = build_participant_state({"battle_only": battle_only})
    assert "preset_bookmarks" not in public["battle_only"]
    assert "preset_bookmarks" in battle_only


def _patch_catalog_routes(monkeypatch, store, state, context):
    emits = []
    monkeypatch.setattr(catalog_v3_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(catalog_v3_routes, "catalog_request_context", lambda _data: dict(context))
    monkeypatch.setattr(catalog_v3_routes, "load_store", lambda: store)
    monkeypatch.setattr(catalog_v3_routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(catalog_v3_routes, "save_specific_room_state", lambda _room: True)
    monkeypatch.setattr(
        catalog_v3_routes,
        "mutate_store",
        lambda mutator: (mutator(store), store)[1],
    )
    monkeypatch.setattr(
        catalog_v3_routes.socketio,
        "emit",
        lambda event, payload=None, to=None: emits.append((event, payload or {}, to)),
    )
    return emits


def test_collection_and_metadata_routes_preserve_acl_and_classify(monkeypatch):
    store = {
        "character_presets": {"char": _record("char", owner="u_gm")},
        "enemy_formations": {},
        "ally_formations": {},
        "stage_presets": {},
        "catalog_collections": {},
    }
    state = {"battle_only": {"preset_bookmarks": []}}
    context = {
        "room": "room",
        "room_role": "gm",
        "user_id": "u_gm",
        "user_info": {"username": "GM"},
        "is_app_admin": False,
    }
    emits = _patch_catalog_routes(monkeypatch, store, state, context)

    catalog_v3_routes.handle_bo_collection_save({
        "room": "room",
        "payload": {
            "id": "scenario_2",
            "name": "Scenario 2",
            "sections": [{"id": "battle_1", "name": "Battle 1", "sort_order": 1}],
        },
    })
    assert store["catalog_collections"]["scenario_2"]["access_control"]["owner_user_id"] == "u_gm"
    assert any(event == "bo_collection_saved" for event, _, _ in emits)

    catalog_v3_routes.handle_bo_record_metadata_save({
        "room": "room",
        "record_type": "character",
        "id": "char",
        "expected_updated_at": store["character_presets"]["char"].get("updated_at", 0),
        "catalog_meta": {
            "collection_id": "scenario_2",
            "section_id": "battle_1",
            "labels": ["No.2"],
            "sort_order": 2,
            "archived": False,
        },
    })
    meta = store["character_presets"]["char"]["catalog_meta"]
    assert meta["collection_id"] == "scenario_2"
    assert meta["section_id"] == "battle_1"
    assert store["character_presets"]["char"]["access_control"]["owner_user_id"] == "u_gm"


def test_room_bookmark_is_idempotent_and_redacts_lost_access(monkeypatch):
    store = {
        "character_presets": {},
        "enemy_formations": {},
        "ally_formations": {},
        "stage_presets": {"stage": _record("stage", owner="u_gm")},
        "catalog_collections": {},
    }
    state = {"battle_only": {"preset_bookmarks": []}}
    context = {
        "room": "room",
        "room_role": "gm",
        "user_id": "u_gm",
        "user_info": {"username": "GM"},
        "is_app_admin": False,
    }
    emits = _patch_catalog_routes(monkeypatch, store, state, context)

    payload = {"room": "room", "target_type": "stage", "target_id": "stage"}
    catalog_v3_routes.handle_bo_bookmark_save(payload)
    catalog_v3_routes.handle_bo_bookmark_save(payload)
    assert len(state["battle_only"]["preset_bookmarks"]) == 1

    store["stage_presets"]["stage"]["access_control"] = {
        "owner_user_id": "another_user",
        "editor_user_ids": [],
        "viewer_mode": "restricted",
        "viewer_user_ids": [],
    }
    catalog_v3_routes.handle_bo_bookmark_list({"room": "room"})
    rows = [payload for event, payload, _ in emits if event == "bo_bookmark_list"]
    assert rows[-1]["bookmarks"][0]["available"] is False
    assert "another_user" not in str(rows[-1])
