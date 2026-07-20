import copy

import pytest

from manager import room_preset_apply


SAMPLE_ENEMY_JSON = {
    "kind": "character",
    "data": {
        "name": "Goblin",
        "status": [
            {"label": "HP", "value": 20, "max": 20},
            {"label": "MP", "value": 5, "max": 5},
            {"label": "FP", "value": 0, "max": 0},
        ],
        "params": [{"label": "\u901f\u5ea6", "value": "7"}],
        "commands": "1d6 attack",
    },
}


def _store():
    return {
        "character_presets": {
            "enemy_1": {
                "id": "enemy_1",
                "name": "GoblinPreset",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_ENEMY_JSON,
            },
            "ally_only": {
                "id": "ally_only",
                "name": "AllyOnly",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_ENEMY_JSON,
            },
            "gm_enemy": {
                "id": "gm_enemy",
                "name": "SecretEnemy",
                "visibility": "gm",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_ENEMY_JSON,
            },
        },
        "enemy_formations": {
            "form_1": {
                "id": "form_1",
                "name": "Two Goblins",
                "visibility": "public",
                "members": [{"preset_id": "enemy_1", "count": 2}],
            }
        },
        "stage_presets": {
            "stage_1": {
                "id": "stage_1",
                "name": "Cave",
                "visibility": "public",
                "enemy_formation_id": "form_1",
                "sort_key": 10,
                "background": {"background_image": "https://example.test/cave.png", "background_scale": 1.2},
                "field_effect_profile": {
                    "version": 1,
                    "rules": [{
                        "rule_id": "fog",
                        "display_name": "濃霧",
                        "description": "視界を遮る霧",
                        "flavor_text": "洞窟に冷たい霧が満ちる。",
                        "type": "SPEED_ROLL_MOD",
                        "scope": "ALL",
                        "value": -1,
                    }],
                },
                "stage_avatar": {"enabled": True, "name": "Cave Spirit", "description": "watcher", "icon": "cave"},
            }
        },
    }


def _state():
    return {
        "play_mode": "normal",
        "battle_mode": "pvp",
        "characters": [
            {"id": "ally_1", "name": "Ally", "type": "ally", "x": 1, "y": 1},
            {"id": "old_enemy", "name": "Old", "type": "enemy", "x": 15, "y": 5},
        ],
        "character_owners": {"ally_1": "Alice", "old_enemy": "GM"},
        "timeline": [{"id": "tl_old", "char_id": "old_enemy", "speed": 1}],
        "active_match": {
            "is_active": True,
            "match_type": "duel",
            "attacker_id": "ally_1",
            "defender_id": "old_enemy",
            "targets": [],
            "attacker_data": {},
            "defender_data": {},
        },
        "map_data": {"width": 20, "height": 15, "gridSize": 64},
        "battle_state": {
            "slots": {"slot_old": {"actor_id": "old_enemy", "team": "enemy"}},
            "timeline": ["slot_old"],
            "intents": {"slot_old": {"skill_id": "s"}},
        },
        "ai_target_arrows": [{"from_id": "old_enemy", "to_id": "ally_1"}],
    }


def _gm():
    return {"username": "GM", "attribute": "GM", "user_id": "u_gm"}


def _player():
    return {"username": "Alice", "attribute": "Player", "user_id": "u_1"}


@pytest.fixture(autouse=True)
def _patch_runtime_hooks(monkeypatch):
    monkeypatch.setattr(room_preset_apply, "apply_passive_effect_buffs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(room_preset_apply, "process_battle_start", lambda *_args, **_kwargs: None)


def test_room_preset_catalog_exposes_only_enemy_usable_rows_for_player():
    catalog = room_preset_apply.build_room_preset_catalog(user_info=_player(), store=_store())

    assert list(catalog["enemy_presets"].keys()) == ["enemy_1"]
    assert catalog["sorted_enemy_preset_ids"] == ["enemy_1"]
    assert list(catalog["enemy_formations"].keys()) == ["form_1"]
    assert list(catalog["stage_presets"].keys()) == ["stage_1"]
    assert catalog["can_manage"] is False


def test_apply_enemy_formation_replaces_existing_enemies_and_keeps_allies():
    state = _state()

    summary = room_preset_apply.apply_enemy_formation_to_room_state(
        state,
        "form_1",
        user_info=_gm(),
        store=_store(),
        room="room_t",
    )

    allies = [c for c in state["characters"] if c.get("type") == "ally"]
    enemies = [c for c in state["characters"] if c.get("type") == "enemy"]
    assert [c["id"] for c in allies] == ["ally_1"]
    assert len(enemies) == 2
    assert all(c["name"] == "Goblin" for c in enemies)
    assert all(c["x"] >= 0 and c["y"] >= 0 for c in enemies)
    assert "old_enemy" not in state["character_owners"]
    assert state["timeline"] == []
    assert state["battle_state"]["slots"] == {}
    assert state["battle_state"]["intents"] == {}
    assert state["active_match"]["is_active"] is False
    assert state["battle_mode"] == "pve"
    assert summary["mode"] == "replace"
    assert summary["removed_enemy_ids"] == ["old_enemy"]
    assert summary["added_enemy_count"] == 2


def test_apply_enemy_preset_appends_by_default():
    state = _state()

    summary = room_preset_apply.apply_enemy_preset_to_room_state(
        state,
        "enemy_1",
        count=1,
        user_info=_gm(),
        store=_store(),
        room="room_t",
    )

    enemies = [c for c in state["characters"] if c.get("type") == "enemy"]
    assert len(enemies) == 2
    assert any(c["id"] == "old_enemy" for c in enemies)
    assert summary["mode"] == "append"
    assert summary["added_enemy_count"] == 1
    assert summary["removed_enemy_count"] == 0


def test_apply_stage_preset_respects_checkbox_options_without_enemy_replacement():
    state = _state()

    summary = room_preset_apply.apply_stage_preset_to_room_state(
        state,
        "stage_1",
        apply_options={
            "enemy_formation": False,
            "background": True,
            "field_effects": True,
            "stage_avatar": True,
        },
        user_info=_gm(),
        store=_store(),
        room="room_t",
    )

    enemies = [c for c in state["characters"] if c.get("type") == "enemy"]
    assert [c["id"] for c in enemies] == ["old_enemy"]
    assert state["battle_map_data"]["background_image"] == "https://example.test/cave.png"
    assert state["map_data"]["backgroundImage"] == "https://example.test/cave.png"
    assert state["field_effects"][0]["field_id"] == "fog"
    assert state["field_effects"][0]["source_id"] == "stage_1"
    assert state["stage_field_effect_profile"]["rules"][0]["display_name"] == "濃霧"
    assert state["stage_field_effect_profile"]["rules"][0]["description"] == "視界を遮る霧"
    assert state["stage_field_effect_profile"]["rules"][0]["flavor_text"] == "洞窟に冷たい霧が満ちる。"
    assert state["stage_avatar_profile"]["name"] == "Cave Spirit"
    assert state["stage_avatar_enabled"] is True
    assert summary["applied"] == {
        "enemy_formation": False,
        "background": True,
        "field_effects": True,
        "stage_avatar": True,
    }


def test_apply_stage_preset_can_apply_enemy_formation_with_default_replace():
    state = _state()

    summary = room_preset_apply.apply_stage_preset_to_room_state(
        state,
        "stage_1",
        apply_options={
            "enemy_formation": True,
            "background": False,
            "field_effects": False,
            "stage_avatar": False,
        },
        user_info=_gm(),
        store=_store(),
        room="room_t",
    )

    enemies = [c for c in state["characters"] if c.get("type") == "enemy"]
    assert len(enemies) == 2
    assert "old_enemy" not in [c["id"] for c in enemies]
    assert summary["applied"]["enemy_formation"] is True
    assert summary["enemy_formation"]["formation_id"] == "form_1"


def test_apply_stage_preset_preserves_disabled_stage_avatar_flag():
    state = _state()
    store = _store()
    store["stage_presets"]["stage_1"]["stage_avatar"]["enabled"] = False

    summary = room_preset_apply.apply_stage_preset_to_room_state(
        state,
        "stage_1",
        apply_options={
            "enemy_formation": False,
            "background": False,
            "field_effects": False,
            "stage_avatar": True,
        },
        user_info=_gm(),
        store=store,
        room="room_t",
    )

    assert state["stage_avatar_profile"]["name"] == "Cave Spirit"
    assert state["stage_avatar_profile"]["enabled"] is False
    assert state["stage_avatar_enabled"] is False
    assert summary["stage_avatar"]["enabled"] is False


def test_enemy_formation_append_mode_is_reserved_for_future_option():
    with pytest.raises(room_preset_apply.RoomPresetError) as exc:
        room_preset_apply.apply_enemy_formation_to_room_state(
            _state(),
            "form_1",
            user_info=_gm(),
            store=_store(),
            mode="append",
        )

    assert exc.value.code == "unsupported_mode"


def test_runtime_enemy_preserves_normalized_tag_state():
    record = copy.deepcopy(_store()["character_presets"]["enemy_1"])
    record["character_json"]["data"].update({
        "tag_ids": [" 種別:瓦礫 ", "機械", "種別:瓦礫"],
        "disabled_tag_ids": ["機械", "未知"],
    })

    enemy = room_preset_apply.build_runtime_enemy_from_preset(record, 1)

    assert enemy["tag_ids"] == ["種別:瓦礫", "機械"]
    assert enemy["disabled_tag_ids"] == ["機械"]
