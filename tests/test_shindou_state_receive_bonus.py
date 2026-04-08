import manager.game_logic as game_logic
import manager.buff_catalog as buff_catalog
from manager.game_logic import process_skill_effects
from manager.utils import apply_buff


def _extract_apply_state_values(changes, state_name):
    return [c[3] for c in changes if c[1] == "APPLY_STATE" and c[2] == state_name]


def _make_receive_bonus_buff(value, *, consume=False, count=None):
    return {
        "name": "震盪",
        "delay": 0,
        "lasting": 2,
        **({"count": int(count)} if count is not None else {}),
        "data": {
            "state_receive_bonus": [{
                "stat": "破裂",
                "operation": "FIXED",
                "value": int(value),
                "consume": bool(consume),
            }]
        },
    }


def test_apply_state_rupture_gets_receive_bonus(sample_actor, sample_target):
    sample_target["special_buffs"] = [_make_receive_bonus_buff(2)]
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE",
        "target": "target",
        "state_name": "破裂",
        "value": 3,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)
    assert _extract_apply_state_values(changes, "破裂") == [5]
    assert not [c for c in changes if c[1] == "REMOVE_BUFF" and c[2] == "震盪"]


def test_apply_state_non_rupture_is_not_affected(sample_actor, sample_target):
    sample_target["special_buffs"] = [_make_receive_bonus_buff(2)]
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE",
        "target": "target",
        "state_name": "出血",
        "value": 3,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)
    assert _extract_apply_state_values(changes, "出血") == [3]


def test_apply_state_negative_rupture_is_not_affected(sample_actor, sample_target):
    sample_target["special_buffs"] = [_make_receive_bonus_buff(2)]
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE",
        "target": "target",
        "state_name": "破裂",
        "value": -3,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)
    assert _extract_apply_state_values(changes, "破裂") == [-3]


def test_apply_state_receive_bonus_with_consume_applies_once(sample_actor, sample_target):
    sample_target["special_buffs"] = [_make_receive_bonus_buff(2, consume=True)]
    effects = [
        {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "破裂",
            "value": 3,
        },
        {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "破裂",
            "value": 3,
        },
    ]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)
    assert _extract_apply_state_values(changes, "破裂") == [5, 3]

    remove_changes = [c for c in changes if c[1] == "REMOVE_BUFF" and c[2] == "震盪"]
    assert len(remove_changes) == 1
    assert remove_changes[0][0].get("id") == sample_target["id"]


def test_apply_state_per_n_rupture_gets_receive_bonus(sample_actor, sample_target):
    sample_target["special_buffs"] = [_make_receive_bonus_buff(2)]
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE_PER_N",
        "source": "self",
        "source_param": "FP",
        "per_N": 1,
        "target": "target",
        "state_name": "破裂",
        "value": 1,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)
    # sample_actor の FP は conftest 上 3。3//1 * 1 + 受け手側+2 = 5
    assert _extract_apply_state_values(changes, "破裂") == [5]


def test_source_and_receive_bonus_stack(sample_actor, sample_target):
    sample_actor["special_buffs"] = [{
        "name": "付与者補正",
        "delay": 0,
        "lasting": 2,
        "data": {
            "state_bonus": [{
                "stat": "破裂",
                "operation": "FIXED",
                "value": 1,
                "consume": False,
            }]
        },
    }]
    sample_target["special_buffs"] = [_make_receive_bonus_buff(2)]
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE",
        "target": "target",
        "state_name": "破裂",
        "value": 3,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)
    assert _extract_apply_state_values(changes, "破裂") == [6]


def test_apply_state_receive_bonus_uses_buff_count_stack(sample_actor, sample_target):
    # 1スタックあたり+1、count=2 なので最終的に +2 される
    sample_target["special_buffs"] = [_make_receive_bonus_buff(1, count=2)]
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE",
        "target": "target",
        "state_name": "破裂",
        "value": 3,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)
    assert _extract_apply_state_values(changes, "破裂") == [5]


def test_apply_state_receive_bonus_falls_back_to_buff_id_catalog_effect(sample_actor, sample_target, monkeypatch):
    sample_target["special_buffs"] = [{
        "name": "震盪",
        "buff_id": "Bu-TestShindou",
        "delay": 0,
        "lasting": 2,
        "data": {"count": 2},  # ルール本体は持たない（カタログ解決前提）
    }]
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE",
        "target": "target",
        "state_name": "破裂",
        "value": 3,
    }]

    monkeypatch.setattr(game_logic, "get_buff_effect", lambda _name: None)
    monkeypatch.setattr(
        buff_catalog,
        "get_buff_by_id",
        lambda _bid: {
            "id": "Bu-TestShindou",
            "name": "震盪",
            "effect": {
                "state_receive_bonus": [{
                    "stat": "破裂",
                    "operation": "FIXED",
                    "value": 1,
                    "consume": False,
                }]
            },
        },
    )

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)
    # 1スタックあたり+1、count=2 なので +2
    assert _extract_apply_state_values(changes, "破裂") == [5]


def test_shindou_buff_catalog_has_state_receive_bonus_rule():
    buff = buff_catalog.get_buff_by_id("Bu-29")
    assert isinstance(buff, dict)

    effect = buff.get("effect")
    assert isinstance(effect, dict)

    rules = effect.get("state_receive_bonus")
    assert isinstance(rules, list) and rules

    matched = False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if str(rule.get("stat")) != "破裂":
            continue
        try:
            val = int(rule.get("value", 0))
        except Exception:
            val = 0
        if val == 1:
            matched = True
            break

    assert matched, "Bu-29 must define state_receive_bonus for 破裂 (+1 per stack)."


def test_shindou_reapply_stacks_count_and_keeps_longer_lasting():
    target = {"id": "T-1", "name": "Target", "special_buffs": []}

    apply_buff(target, "震盪", 3, 0, data={"buff_id": "Bu-29", "count": 2})
    apply_buff(target, "震盪", 1, 0, data={"buff_id": "Bu-29", "count": 2})

    assert len(target["special_buffs"]) == 1
    buff = target["special_buffs"][0]
    assert buff.get("name") == "震盪"
    assert int(buff.get("count", 0)) == 4
    assert int((buff.get("data") or {}).get("count", 0)) == 4
    assert int(buff.get("lasting", 0)) == 3


def test_shindou_reapply_without_count_treated_as_one_and_can_extend_lasting():
    target = {"id": "T-2", "name": "Target", "special_buffs": []}

    apply_buff(target, "震盪", 1, 0, data={"buff_id": "Bu-29", "count": 2})
    apply_buff(target, "震盪", 5, 0, data={"buff_id": "Bu-29"})

    assert len(target["special_buffs"]) == 1
    buff = target["special_buffs"][0]
    assert int(buff.get("count", 0)) == 3
    assert int((buff.get("data") or {}).get("count", 0)) == 3
    assert int(buff.get("lasting", 0)) == 5
