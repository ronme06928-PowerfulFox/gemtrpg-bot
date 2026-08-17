import copy

import pytest

from manager.preset_deployment import (
    MAX_DEPLOYED_CHARACTERS,
    PresetDeploymentError,
    apply_deployment,
    build_deployment_catalog,
    preview_deployment,
)


def _acl(owner="u_gm"):
    return {
        "owner_user_id": owner,
        "editor_user_ids": [],
        "viewer_mode": "public",
        "viewer_user_ids": [],
    }


def _character(record_id, name, *, allow_ally=True, allow_enemy=True):
    return {
        "id": record_id,
        "name": name,
        "allow_ally": allow_ally,
        "allow_enemy": allow_enemy,
        "access_control": _acl(),
        "catalog_meta": {"collection_id": "col_s2", "section_id": "chars"},
        "character_json": {
            "data": {
                "name": name,
                "status": [
                    {"label": "HP", "value": 20, "max": 20},
                    {"label": "MP", "value": 5, "max": 5},
                ],
                "params": [],
                "states": [],
                "special_buffs": [],
            }
        },
    }


def _store():
    return {
        "version": 3,
        "character_presets": {
            "c_enemy": _character("c_enemy", "敵素材"),
            "c_ally": _character("c_ally", "味方素材"),
        },
        "enemy_formations": {
            "ef_1": {
                "id": "ef_1",
                "name": "敵編成",
                "members": [{"preset_id": "c_enemy", "count": 2}],
                "access_control": _acl(),
                "catalog_meta": {"collection_id": "col_s2", "section_id": "encounters"},
            }
        },
        "ally_formations": {
            "af_1": {
                "id": "af_1",
                "name": "味方編成",
                "members": [{"preset_id": "c_ally", "user_id": "offline_user"}],
                "access_control": _acl(),
                "catalog_meta": {"collection_id": "col_s2", "section_id": "parties"},
            }
        },
        "stage_presets": {
            "st_1": {
                "id": "st_1",
                "name": "試験ステージ",
                "enemy_formation_id": "ef_1",
                "ally_formation_id": "af_1",
                "required_ally_count": 1,
                "background_image": "https://example.invalid/stage.png",
                "field_effect_profile": {"version": 1, "rules": []},
                "stage_avatar": {"enabled": True, "name": "案内役"},
                "access_control": _acl(),
                "catalog_meta": {"collection_id": "col_s2", "section_id": "stages"},
            }
        },
        "catalog_collections": {
            "col_s2": {
                "id": "col_s2",
                "name": "シナリオ02",
                "sort_order": 10,
                "sections": [
                    {"id": "chars", "name": "素材", "sort_order": 10},
                    {"id": "encounters", "name": "戦闘", "sort_order": 20},
                ],
                "access_control": _acl(),
            }
        },
    }


def _context():
    return {
        "user_id": "u_gm",
        "room_role": "gm",
        "is_app_admin": False,
        "gm_user": {"user_id": "u_gm", "username": "GM太郎"},
        "active_users": {"u_gm": "GM太郎", "u_player": "PL花子"},
    }


def _normal_state():
    return {
        "play_mode": "normal",
        "characters": [
            {"id": "old_a", "name": "既存味方", "type": "ally", "x": 1, "y": 1},
            {"id": "old_e", "name": "既存敵", "type": "enemy", "x": 10, "y": 1},
        ],
        "character_owners": {"old_a": "PL", "old_e": "GM"},
        "map_data": {"width": 20, "height": 15},
    }


def test_catalog_returns_all_record_types_and_collection_counts():
    catalog = build_deployment_catalog(
        _store(),
        user_id="u_gm",
        room_role="gm",
        users=[{"user_id": "u_gm", "username": "GM太郎"}],
    )

    assert set(catalog["records"]) == {"character", "enemy_formation", "ally_formation", "stage"}
    assert catalog["records"]["stage"]["st_1"]["enemy_formation_id"] == "ef_1"
    assert catalog["collection_counts"]["col_s2"] == 5
    assert catalog["can_deploy"] is True


def test_normal_stage_and_single_character_apply_atomically():
    state = _normal_state()
    request_data = {
        "target_mode": "normal",
        "stage": {"record_id": "st_1", "apply": {}},
        "characters": [{"record_id": "c_enemy", "side": "enemy", "count": 1}],
    }

    summary, logs = apply_deployment(state, request_data, _store(), **_context())

    assert summary["added"] == {"ally": 1, "enemy": 3}
    assert summary["removed"] == {"ally": 0, "enemy": 1}
    assert logs == []
    assert any(char["id"] == "old_a" for char in state["characters"])
    assert not any(char["id"] == "old_e" for char in state["characters"])
    allies = [char for char in state["characters"] if char.get("type") == "ally" and char["id"] != "old_a"]
    assert allies[0]["owner"] == "GM太郎"
    assert allies[0]["owner_id"] == "u_gm"
    assert state["battle_map_data"]["background_image"] == "https://example.invalid/stage.png"
    assert state["stage_avatar_profile"]["name"] == "案内役"


def test_normal_deployment_assigns_unique_enemy_numbers_to_batch():
    state = _normal_state()
    store = _store()
    store["character_presets"]["c_enemy"]["character_json"]["data"].update({
        "name": "敵素材 [敵 1]",
        "baseName": "敵素材",
    })

    apply_deployment(
        state,
        {
            "target_mode": "normal",
            "characters": [{"record_id": "c_enemy", "side": "enemy", "count": 3}],
        },
        store,
        **_context(),
    )

    added = [char for char in state["characters"] if char["id"] not in {"old_a", "old_e"}]
    assert [char["name"] for char in added] == [
        "敵素材 [敵 1]",
        "敵素材 [敵 2]",
        "敵素材 [敵 3]",
    ]


def test_preview_does_not_mutate_room_state():
    state = _normal_state()
    before = copy.deepcopy(state)

    summary = preview_deployment(
        state,
        {"target_mode": "normal", "formations": {"enemy": {"record_id": "ef_1"}}},
        _store(),
        **_context(),
    )

    assert summary["added"]["enemy"] == 2
    assert state == before


def test_invalid_reference_does_not_change_state():
    state = _normal_state()
    before = copy.deepcopy(state)

    with pytest.raises(PresetDeploymentError) as exc:
        apply_deployment(
            state,
            {
                "target_mode": "normal",
                "characters": [{"record_id": "missing", "side": "enemy", "count": 1}],
            },
            _store(),
            **_context(),
        )

    assert exc.value.code == "not_found"
    assert state == before


def test_deployment_limit_accepts_100_and_rejects_101():
    state = _normal_state()
    accepted = preview_deployment(
        state,
        {
            "target_mode": "normal",
            "characters": [{"record_id": "c_enemy", "side": "enemy", "count": MAX_DEPLOYED_CHARACTERS}],
        },
        _store(),
        **_context(),
    )
    assert accepted["new_character_count"] == 100

    with pytest.raises(PresetDeploymentError) as exc:
        preview_deployment(
            state,
            {
                "target_mode": "normal",
                "characters": [{"record_id": "c_enemy", "side": "enemy", "count": 101}],
            },
            _store(),
            **_context(),
        )
    assert exc.value.code == "deployment_limit_exceeded"


def test_battle_only_stage_replaces_draft_and_single_character_appends():
    state = {
        "play_mode": "battle_only",
        "battle_only": {
            "status": "draft",
            "ally_entries": [{"preset_id": "old_ally", "user_id": "u_player"}],
            "enemy_entries": [{"preset_id": "old_enemy", "count": 4}],
        },
    }
    request_data = {
        "target_mode": "battle_only",
        "stage": {"record_id": "st_1", "apply": {}},
        "characters": [{"record_id": "c_enemy", "side": "enemy", "count": 1}],
    }

    summary, _ = apply_deployment(state, request_data, _store(), **_context())

    bo = state["battle_only"]
    assert bo["selected_stage_id"] == "st_1"
    assert bo["ally_entries"] == [{"preset_id": "c_ally", "user_id": "u_gm"}]
    assert sum(row["count"] for row in bo["enemy_entries"]) == 3
    assert summary["removed"] == {"ally": 1, "enemy": 4}
    assert summary["ready"] is True
    assert summary["issues"] == []
    assert bo["stage_background_profile"]["background_image"] == "https://example.invalid/stage.png"
    assert state["play_mode"] == "battle_only"


def test_battle_only_preview_reports_assignment_and_required_count_issues():
    store = _store()
    store["stage_presets"]["st_1"]["required_ally_count"] = 2
    context = _context()
    context["active_users"] = {"u_player": "PL花子"}

    summary = preview_deployment(
        {"play_mode": "battle_only", "battle_only": {"status": "draft"}},
        {"target_mode": "battle_only", "stage": {"record_id": "st_1", "apply": {}}},
        store,
        **context,
    )

    assert summary["ready"] is False
    assert summary["can_apply"] is True
    assert any("担当ユーザー" in issue for issue in summary["issues"])
    assert any("味方人数が不一致" in issue for issue in summary["issues"])
