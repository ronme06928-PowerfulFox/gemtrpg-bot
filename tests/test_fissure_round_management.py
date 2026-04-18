from manager.game_logic import process_skill_effects
from manager.utils import apply_buff, get_status_value, set_status_value
from manager.battle import core as battle_core
from plugins.fissure import FissureEffect


def _state_value(char, name):
    for row in char.get("states", []):
        if isinstance(row, dict) and row.get("name") == name:
            return int(row.get("value", 0))
    return 0


def test_apply_state_with_rounds_routes_to_fissure_buff(sample_actor, sample_target):
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE",
        "target": "target",
        "state_name": "亀裂",
        "value": 1,
        "rounds": 3,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)

    fissure_apply_state = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "亀裂"]
    fissure_apply_buff = [c for c in changes if c[1] == "APPLY_BUFF" and c[2] == "亀裂_R3"]
    fissure_flag = [c for c in changes if c[1] == "SET_FLAG" and c[2] == "fissure_received_this_round"]

    assert len(fissure_apply_state) == 0
    assert len(fissure_apply_buff) == 1
    payload = fissure_apply_buff[0][3]
    assert int(payload.get("lasting", 0)) == 3
    assert payload.get("data", {}).get("buff_id") == "Bu-Fissure"
    assert int(payload.get("data", {}).get("count", 0)) == 1
    assert len(fissure_flag) == 1


def test_apply_state_with_rounds_uses_crackonce_bonus_and_consumes(sample_actor, sample_target):
    sample_actor["special_buffs"] = [{
        "name": "突き崩す_CrackOnce1",
        "delay": 0,
        "lasting": 999,
        "data": {},
    }]
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE",
        "target": "target",
        "state_name": "亀裂",
        "value": 1,
        "rounds": 3,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)

    buff_changes = [c for c in changes if c[1] == "APPLY_BUFF" and c[2] == "亀裂_R3"]
    remove_changes = [c for c in changes if c[1] == "REMOVE_BUFF" and c[2] == "突き崩す_CrackOnce1"]
    assert len(buff_changes) == 1
    assert len(remove_changes) == 1
    assert int(buff_changes[0][3].get("data", {}).get("count", 0)) == 2


def test_apply_state_without_rounds_keeps_legacy_permanent_behavior(sample_actor, sample_target):
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE",
        "target": "target",
        "state_name": "亀裂",
        "value": 1,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)

    fissure_apply_state = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "亀裂"]
    fissure_apply_buff = [c for c in changes if c[1] == "APPLY_BUFF" and c[2].startswith("亀裂_R")]
    assert len(fissure_apply_state) == 1
    assert fissure_apply_state[0][3] == 1
    assert len(fissure_apply_buff) == 0


def test_apply_state_per_n_with_rounds_routes_to_fissure_buff_and_bonus(sample_actor, sample_target):
    sample_actor["special_buffs"] = [{
        "name": "突き崩す_CrackOnce1",
        "delay": 0,
        "lasting": 999,
        "data": {},
    }]
    effects = [{
        "timing": "HIT",
        "type": "APPLY_STATE_PER_N",
        "source": "self",
        "source_param": "FP",
        "per_N": 1,
        "target": "target",
        "state_name": "亀裂",
        "value": 1,
        "rounds": 2,
    }]

    _, _, changes = process_skill_effects(effects, "HIT", sample_actor, sample_target)
    buff_changes = [c for c in changes if c[1] == "APPLY_BUFF" and c[2] == "亀裂_R2"]
    assert len(buff_changes) == 1
    # FP(3)//1 * 1 = 3, CrackOnce +1 => 4
    assert int(buff_changes[0][3].get("data", {}).get("count", 0)) == 4


def test_apply_buff_bu_fissure_separates_buckets_when_remaining_rounds_differ(sample_target):
    char = sample_target
    set_status_value(char, "亀裂", 0)
    char["special_buffs"] = []

    apply_buff(
        char,
        "亀裂_R4",
        4,
        0,
        data={"buff_id": "Bu-Fissure", "count": 3, "original_rounds": 4},
    )
    assert get_status_value(char, "亀裂") == 3
    assert len(char["special_buffs"]) == 1
    assert int(char["special_buffs"][0].get("count", 0)) == 3

    # Simulate one round passed before re-application.
    char["special_buffs"][0]["lasting"] = 3
    apply_buff(
        char,
        "亀裂_R4",
        4,
        0,
        data={"buff_id": "Bu-Fissure", "count": 2, "original_rounds": 4},
    )
    assert get_status_value(char, "亀裂") == 5
    assert len(char["special_buffs"]) == 2
    counts_after_second = sorted(int(b.get("count", 0)) for b in char["special_buffs"])
    assert counts_after_second == [2, 3]
    lasting_after_second = sorted(int(b.get("lasting", 0)) for b in char["special_buffs"])
    assert lasting_after_second == [3, 4]

    apply_buff(
        char,
        "亀裂_R3",
        3,
        0,
        data={"buff_id": "Bu-Fissure", "count": 1, "original_rounds": 3},
    )
    assert get_status_value(char, "亀裂") == 6
    assert len(char["special_buffs"]) == 2
    buckets = sorted(
        ((int(b.get("lasting", 0)), int(b.get("count", 0))) for b in char["special_buffs"]),
        key=lambda row: row[0],
    )
    assert buckets == [(3, 4), (4, 2)]


def test_process_simple_round_end_expires_fissure_bucket_and_subtracts(monkeypatch):
    char = {
        "id": "t1",
        "name": "target",
        "hp": 100,
        "states": [{"name": "亀裂", "value": 5}],
        "special_buffs": [{
            "name": "亀裂_R3",
            "buff_id": "Bu-Fissure",
            "delay": 0,
            "lasting": 1,
            "count": 2,
            "data": {"original_rounds": 3, "fissure_count": 2},
        }],
    }
    state = {"characters": [char]}

    monkeypatch.setattr(battle_core, "apply_origin_bonus_buffs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(battle_core, "process_summon_round_end", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(battle_core, "process_granted_skill_round_end", lambda *_args, **_kwargs: [])

    battle_core.process_simple_round_end(state, room="room_t")

    assert _state_value(char, "亀裂") == 3
    assert len(char["special_buffs"]) == 0


def test_process_simple_round_end_updates_fissure_bucket_name_to_remaining_rounds(monkeypatch):
    char = {
        "id": "t2",
        "name": "target2",
        "hp": 100,
        "states": [{"name": "亀裂", "value": 4}],
        "special_buffs": [{
            "name": "亀裂_R4",
            "buff_id": "Bu-Fissure",
            "delay": 0,
            "lasting": 4,
            "count": 4,
            "data": {"original_rounds": 4, "fissure_count": 4},
        }],
    }
    state = {"characters": [char]}

    monkeypatch.setattr(battle_core, "apply_origin_bonus_buffs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(battle_core, "process_summon_round_end", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(battle_core, "process_granted_skill_round_end", lambda *_args, **_kwargs: [])

    battle_core.process_simple_round_end(state, room="room_t")

    assert len(char["special_buffs"]) == 1
    bucket = char["special_buffs"][0]
    assert int(bucket.get("lasting", 0)) == 3
    assert bucket.get("name") == "亀裂_R3"


def test_fissure_collapse_returns_clear_changes_and_mutates_sim_target(sample_target):
    set_status_value(sample_target, "亀裂", 5)
    sample_target["special_buffs"] = [
        {"name": "亀裂_R4", "buff_id": "Bu-Fissure", "count": 3, "lasting": 3, "delay": 0, "data": {"original_rounds": 4}},
        {"name": "亀裂_R2", "buff_id": "Bu-Fissure", "count": 2, "lasting": 1, "delay": 0, "data": {"original_rounds": 2}},
    ]
    effect = FissureEffect(mode="damage")

    changes, logs = effect.apply(None, sample_target, {"damage_per_fissure": 4}, {})

    assert any(c[1] == "CUSTOM_DAMAGE" and c[3] == 20 for c in changes)
    assert any(c[1] == "APPLY_STATE" and c[2] == "亀裂" and c[3] == -5 for c in changes)
    remove_names = [c[2] for c in changes if c[1] == "REMOVE_BUFF"]
    assert "亀裂_R4" in remove_names and "亀裂_R2" in remove_names
    assert get_status_value(sample_target, "亀裂") == 0
    assert len(sample_target.get("special_buffs", [])) == 0
    assert logs
