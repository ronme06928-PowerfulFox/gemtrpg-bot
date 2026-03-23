from manager import game_logic
from manager import utils


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
            {"label": "出身", "value": str(origin_id)},
            {"label": "速度", "value": str(speed)},
        ],
        "states": [],
        "special_buffs": [],
        "flags": {},
    }


def test_process_skill_effects_hit_adds_coloration_even_without_skill_effects():
    actor = _make_char("A", utils.ORIGIN_GRAND_LITTERAL_BLANC, "ally")
    target = _make_char("T", 0, "enemy")

    _, logs, changes = game_logic.process_skill_effects([], "HIT", actor, target, context={"characters": [actor, target]})

    assert any("色彩" in str(log) for log in logs)
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
        "チャットパレット": "【ATK】0+1d6",
        "ダイス威力": "1d6",
        "基礎威力": 0,
        "分類": "物理",
        "tags": ["攻撃"],
    }

    preview = game_logic.calculate_skill_preview(actor, target, skill, context={"characters": [actor, target]})

    assert int(preview["skill_details"]["final_power_total_mod"]) == 1
    assert preview["final_command"].endswith("+1")


def test_calculate_skill_preview_grants_final_power_to_any_ally_against_coloration_target():
    actor = _make_char("A", 0, "ally")
    target = _make_char("T", 0, "enemy")
    target["special_buffs"].append({"name": utils.COLORATION_BUFF_NAME})
    skill = {
        "チャットパレット": "ATK+1d6",
        "ダイス威力": "1d6",
        "基礎威力": 0,
        "分類": "攻撃",
        "tags": ["攻撃"],
    }

    preview = game_logic.calculate_skill_preview(actor, target, skill, context={"characters": [actor, target]})

    assert int(preview["skill_details"]["final_power_total_mod"]) == 1
    assert preview["final_command"].endswith("+1")


def test_compute_origin_skill_modifiers_for_flodias_reads_enemy_team_origin():
    actor = _make_char("A", utils.ORIGIN_FLODIAS, "ally")
    target = _make_char("T", 0, "enemy")
    enemy_valwaire = _make_char("V", 13, "enemy")
    skill = {
        "分類": "回避",
        "tags": ["回避"],
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
        "分類": "物理",
        "tags": ["攻撃"],
    }

    mods = utils.compute_origin_skill_modifiers(
        actor,
        target,
        skill,
        context={"characters": [actor, peer, target]},
    )

    assert int(mods["base_power_bonus"]) == 1


def test_round_end_origin_recoveries_cover_existing_and_new_origins():
    mahoroba = _make_char("M", 5)
    altomagia = _make_char("A", utils.ORIGIN_ALTOMAGIA)

    assert utils.get_round_end_origin_recoveries(mahoroba) == {"HP": 3}
    assert utils.get_round_end_origin_recoveries(altomagia) == {"MP": 1}
