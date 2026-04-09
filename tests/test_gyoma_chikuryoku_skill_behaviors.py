import json

from manager.cache_paths import LEGACY_SKILLS_CACHE_FILE, SKILLS_CACHE_FILE, load_json_cache
from manager.game_logic import process_skill_effects
from manager.utils import apply_buff, get_status_value, remove_buff, set_status_value


def _build_char(char_id="char-1", team="ally"):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 100,
        "mp": 10,
        "params": [
            {"label": "物理補正", "value": 0},
            {"label": "魔法補正", "value": 0},
        ],
        "states": [
            {"name": "FP", "value": 0},
            {"name": "MP", "value": 10},
            {"name": "出血", "value": 0},
            {"name": "破裂", "value": 0},
        ],
        "special_buffs": [],
        "SPassive": [],
    }


def _apply_changes(changes):
    for target, change_type, name, value in changes:
        if change_type == "APPLY_STATE":
            current = get_status_value(target, name)
            set_status_value(target, name, current + int(value))
        elif change_type == "REMOVE_BUFF":
            remove_buff(target, name)
        elif change_type == "APPLY_BUFF":
            apply_buff(
                target,
                name,
                value.get("lasting", 0),
                value.get("delay", 0),
                data=value.get("data"),
                count=value.get("count"),
            )


def _load_skill_effects(skill_id):
    skills = load_json_cache(SKILLS_CACHE_FILE, legacy_paths=[LEGACY_SKILLS_CACHE_FILE])
    skill = skills[skill_id]
    rule = json.loads(skill.get("特記処理", "{}") or "{}")
    return rule.get("effects", [])


def _find_buff_count_by_id(char_obj, buff_id):
    for buff in char_obj.get("special_buffs", []):
        if not isinstance(buff, dict):
            continue
        data = buff.get("data") if isinstance(buff.get("data"), dict) else {}
        row_buff_id = buff.get("buff_id") or data.get("buff_id")
        if row_buff_id != buff_id:
            continue
        if buff.get("count") is not None:
            return int(buff.get("count"))
        if data.get("count") is not None:
            return int(data.get("count"))
        return 1
    return 0


def test_mb11_hit_grants_gyoma_4():
    actor = _build_char("actor")
    target = _build_char("target", team="enemy")
    effects = _load_skill_effects("Mb-11")

    _, _, changes = process_skill_effects(effects, "HIT", actor, target, context={"characters": [actor, target]})
    _apply_changes(changes)

    assert _find_buff_count_by_id(actor, "Bu-Gyoma") == 4


def test_mb12_pre_match_consumes_gyoma_and_restores_mp():
    actor = _build_char("actor")
    target = _build_char("target", team="enemy")
    effects = _load_skill_effects("Mb-12")
    apply_buff(actor, "凝魔", -1, 0, data={"buff_id": "Bu-Gyoma"}, count=3)

    _, _, changes = process_skill_effects(
        effects, "PRE_MATCH", actor, target, context={"characters": [actor, target]}
    )
    _apply_changes(changes)

    assert _find_buff_count_by_id(actor, "Bu-Gyoma") == 0
    assert get_status_value(actor, "MP") == 15


def test_mb13_pre_match_consumes_up_to_5_and_adds_final_power():
    actor = _build_char("actor")
    target = _build_char("target", team="enemy")
    effects = _load_skill_effects("Mb-13")
    apply_buff(actor, "凝魔", -1, 0, data={"buff_id": "Bu-Gyoma"}, count=7)

    _, _, changes = process_skill_effects(
        effects, "PRE_MATCH", actor, target, context={"characters": [actor, target]}
    )
    _apply_changes(changes)

    final_mods = [c for c in changes if c[1] == "MODIFY_FINAL_POWER"]
    assert len(final_mods) == 1
    assert int(final_mods[0][3]) == 5
    assert _find_buff_count_by_id(actor, "Bu-Gyoma") == 2


def test_ps11_pre_match_grants_chikuryoku_4():
    actor = _build_char("actor")
    target = _build_char("target", team="enemy")
    effects = _load_skill_effects("Ps-11")

    _, _, changes = process_skill_effects(
        effects, "PRE_MATCH", actor, target, context={"characters": [actor, target]}
    )
    _apply_changes(changes)

    assert _find_buff_count_by_id(actor, "Bu-Chikuryoku") == 4


def test_ps12_end_round_grants_2_and_hit_bonus_only_when_empty():
    actor = _build_char("actor")
    target = _build_char("target", team="enemy")
    effects = _load_skill_effects("Ps-12")

    _, _, hit_changes = process_skill_effects(effects, "HIT", actor, target, context={"characters": [actor, target]})
    _apply_changes(hit_changes)
    assert _find_buff_count_by_id(actor, "Bu-Chikuryoku") == 5

    _, _, end_changes = process_skill_effects(
        effects, "END_ROUND", actor, target, context={"characters": [actor, target]}
    )
    _apply_changes(end_changes)
    assert _find_buff_count_by_id(actor, "Bu-Chikuryoku") == 7


def test_ps13_hit_applies_bleed_and_consumes_chikuryoku_for_fp():
    actor = _build_char("actor")
    target = _build_char("target", team="enemy")
    effects = _load_skill_effects("Ps-13")
    apply_buff(actor, "蓄力", -1, 0, data={"buff_id": "Bu-Chikuryoku"}, count=4)

    _, _, changes = process_skill_effects(effects, "HIT", actor, target, context={"characters": [actor, target]})
    _apply_changes(changes)

    assert get_status_value(target, "出血") == 7
    assert get_status_value(actor, "FP") == 3
    assert _find_buff_count_by_id(actor, "Bu-Chikuryoku") == 0
