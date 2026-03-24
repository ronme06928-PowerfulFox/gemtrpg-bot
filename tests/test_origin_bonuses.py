import pytest

from manager import game_logic
from manager import utils
from manager.battle import core as battle_core


def _make_char(char_id, origin_id, team="ally", speed=10):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 100,
        "maxHp": 100,
        "mp": 10,
        "maxMp": 10,
        "totalSpeed": speed,
        "params": [
            {"label": "蜃ｺ霄ｫ", "value": str(origin_id)},
            {"label": "鬨ｾ貅ｷ・ｺ・ｦ", "value": str(speed)},
        ],
        "states": [],
        "special_buffs": [],
        "flags": {},
        "_origin_id": int(origin_id or 0),
    }


@pytest.fixture(autouse=True)
def _patch_origin_resolvers(monkeypatch):
    def _effective_origin(char_obj):
        if not isinstance(char_obj, dict):
            return 0
        return int(char_obj.get("_origin_id", 0) or 0)

    def _origin_and_bonus(char_obj):
        if not isinstance(char_obj, dict):
            return 0, 0
        return int(char_obj.get("_origin_id", 0) or 0), int(char_obj.get("_bonus_origin_id", 0) or 0)

    monkeypatch.setattr(utils, "get_effective_origin_id", _effective_origin)
    monkeypatch.setattr(utils, "get_origin_and_bonus_ids", _origin_and_bonus)


def test_process_skill_effects_hit_adds_coloration_even_without_skill_effects():
    actor = _make_char("A", utils.ORIGIN_GRAND_LITTERAL_BLANC, "ally")
    target = _make_char("T", 0, "enemy")

    _, _logs, changes = game_logic.process_skill_effects(
        [], "HIT", actor, target, context={"characters": [actor, target]}
    )

    buff_changes = [change for change in changes if change[1] == "APPLY_BUFF"]
    assert buff_changes
    assert buff_changes[0][2] == utils.COLORATION_BUFF_NAME
    assert int(buff_changes[0][3]["lasting"]) == 2
    assert buff_changes[0][3]["data"]["buff_id"] == utils.COLORATION_BUFF_ID


def test_calculate_skill_preview_grants_final_power_against_coloration_target():
    actor = _make_char("A", utils.ORIGIN_GRAND_LITTERAL_BLANC, "ally")
    target = _make_char("T", 0, "enemy")
    target["special_buffs"].append({"name": utils.COLORATION_BUFF_NAME})
    skill = {
        "category": "attack",
        "tags": ["attack"],
    }

    preview = game_logic.calculate_skill_preview(
        actor, target, skill, context={"characters": [actor, target]}
    )

    assert int(preview["skill_details"]["final_power_total_mod"]) == 1
    assert "+1" in str(preview.get("final_command", ""))


def test_calculate_skill_preview_grants_final_power_to_any_ally_against_coloration_target():
    actor = _make_char("A", 0, "ally")
    target = _make_char("T", 0, "enemy")
    target["special_buffs"].append({"name": utils.COLORATION_BUFF_NAME})
    skill = {
        "category": "attack",
        "tags": ["attack"],
    }

    preview = game_logic.calculate_skill_preview(
        actor, target, skill, context={"characters": [actor, target]}
    )

    assert int(preview["skill_details"]["final_power_total_mod"]) == 1
    assert "+1" in str(preview.get("final_command", ""))


def test_compute_origin_skill_modifiers_for_flodias_reads_enemy_team_origin():
    actor = _make_char("A", utils.ORIGIN_FLODIAS, "ally")
    target = _make_char("T", 0, "enemy")
    enemy_valwaire = _make_char("V", 13, "enemy")
    skill = {
        "category": "evade",
        "tags": ["evade"],
    }

    mods = utils.compute_origin_skill_modifiers(
        actor,
        target,
        skill,
        context={"characters": [actor, target, enemy_valwaire]},
    )

    assert int(mods["dice_power_bonus"]) == 2


def test_compute_origin_skill_modifiers_for_emrida_reads_same_speed_peer():
    actor = _make_char("A", utils.ORIGIN_EMRIDA, "ally", speed=11)
    peer = _make_char("B", 0, "enemy", speed=11)
    target = _make_char("T", 0, "enemy", speed=7)
    skill = {
        "category": "attack",
        "tags": ["attack"],
    }

    mods = utils.compute_origin_skill_modifiers(
        actor,
        target,
        skill,
        context={"characters": [actor, peer, target]},
    )

    assert int(mods["base_power_bonus"]) == 1


def test_compute_origin_skill_modifiers_for_emrida_uses_slot_initiative_fallback():
    actor = _make_char("A", utils.ORIGIN_EMRIDA, "ally", speed=11)
    peer = _make_char("B", 0, "enemy", speed=7)
    target = _make_char("T", 0, "enemy", speed=7)
    actor["totalSpeed"] = None
    peer["totalSpeed"] = None
    target["totalSpeed"] = None

    skill = {
        "category": "attack",
        "tags": ["attack"],
    }

    mods = utils.compute_origin_skill_modifiers(
        actor,
        target,
        skill,
        context={
            "characters": [actor, peer, target],
            "battle_state": {
                "slots": {
                    "A_slot": {"actor_id": "A", "initiative": 7, "disabled": False},
                    "B_slot": {"actor_id": "B", "initiative": 7, "disabled": False},
                    "T_slot": {"actor_id": "T", "initiative": 3, "disabled": False},
                }
            },
        },
    )

    assert int(mods["base_power_bonus"]) == 1


def test_round_end_origin_recoveries_cover_existing_and_new_origins():
    mahoroba = _make_char("M", 5)
    altomagia = _make_char("A", utils.ORIGIN_ALTOMAGIA)

    assert utils.get_round_end_origin_recoveries(mahoroba) == {"HP": 3}
    assert utils.get_round_end_origin_recoveries(altomagia) == {"MP": 1}


def test_apply_origin_bonus_buffs_marks_buff_permanent():
    actor = _make_char("A", utils.ORIGIN_ALTOMAGIA)

    utils.apply_origin_bonus_buffs(actor)

    buff = next((b for b in actor["special_buffs"] if b.get("buff_id") == "Bu-23"), None)
    assert buff is not None
    assert int(buff.get("lasting", 0)) == -1
    assert buff.get("is_permanent") is True


def test_process_simple_round_end_restores_origin_bonus_buff(monkeypatch):
    actor = _make_char("A", utils.ORIGIN_ALTOMAGIA)
    state = {"characters": [actor]}

    monkeypatch.setattr(battle_core, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(battle_core, "_update_char_stat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(battle_core, "process_summon_round_end", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(battle_core, "process_granted_skill_round_end", lambda *_args, **_kwargs: [])

    battle_core.process_simple_round_end(state, room="room_t")

    buff_ids = [b.get("buff_id") for b in actor.get("special_buffs", [])]
    assert "Bu-23" in buff_ids
