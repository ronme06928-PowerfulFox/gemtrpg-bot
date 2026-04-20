from manager.utils import apply_buff, get_status_value
from manager.game_logic import check_condition
from manager.battle import common_manager as battle_common


def test_get_status_value_separates_speed_and_speed_value():
    char = {
        "id": "A1",
        "hp": 100,
        "params": [{"label": "速度", "value": 10}],
        "states": [],
        "totalSpeed": 17,
    }

    assert get_status_value(char, "速度") == 10
    assert get_status_value(char, "速度値") == 17


def test_select_resolve_round_start_uses_speed_modifier(monkeypatch):
    char = {
        "id": "A1",
        "name": "ActorA",
        "type": "ally",
        "hp": 100,
        "x": 1,
        "y": 1,
        "is_escaped": False,
        "params": [
            {"label": "速度", "value": 12},
            {"label": "行動回数", "value": 1},
        ],
        "states": [],
        # legacy style entries (no delay/lasting) should be normalized, not immediately cleared
        "special_buffs": [
            {"name": "加速", "buff_id": "Bu-11", "count": 2},
            {"name": "減速", "buff_id": "Bu-12", "count": 1},
            {"name": "Dummy", "buff_id": "Bu-99", "count": 1},
        ],
    }
    state = {
        "round": 1,
        "characters": [char],
        "timeline": [],
        "battle_state": {
            "battle_id": "battle_test",
            "round": 1,
            "phase": "select",
            "slots": {},
            "timeline": [],
            "tiebreak": [],
            "intents": {},
            "redirects": [],
            "resolve_snapshot_intents": {},
            "resolve_snapshot_at": None,
            "resolve_ready": False,
            "resolve_ready_info": {},
            "resolve": {
                "mass_queue": [],
                "single_queue": [],
                "resolved_slots": [],
                "trace": [],
            },
        },
    }
    logs = []

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(
        battle_common,
        "broadcast_log",
        lambda room, message, log_type="info": logs.append((room, message, log_type)),
    )
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})

    payload = battle_common.process_select_resolve_round_start(
        room="room_a",
        battle_id="battle_test",
        round_value=2,
    )

    assert payload is not None
    assert len(payload["timeline"]) == 1

    slot_id = payload["timeline"][0]
    slot = payload["slots"][slot_id]

    # speed 12 -> 12//6=2, modifier(+2-1)=+1, 1d6=1 => initiative 4
    assert slot["initiative"] == 4
    assert slot["speed_stat"] == 12
    assert slot["speed_base"] == 3
    assert slot["speed_modifier"] == 1
    assert slot["speed_roll"] == 1

    assert char["speedRoll"] == 1
    assert char["totalSpeed"] == 4
    assert char["hasActed"] is False

    # speed buffs remain; lifecycle is now managed by round-end decay
    remaining_ids = [b.get("buff_id") for b in char.get("special_buffs", [])]
    assert "Bu-11" in remaining_ids
    assert "Bu-12" in remaining_ids
    assert "Bu-99" in remaining_ids
    haste = next((b for b in char["special_buffs"] if b.get("buff_id") == "Bu-11"), {})
    slow = next((b for b in char["special_buffs"] if b.get("buff_id") == "Bu-12"), {})
    assert int(haste.get("delay", -1)) == 0
    assert int(slow.get("delay", -1)) == 0
    assert int(haste.get("lasting", 0)) == 1
    assert int(slow.get("lasting", 0)) == 1

    assert len(state["timeline"]) == 1
    assert state["timeline"][0]["id"] == slot_id
    assert state["timeline"][0]["char_id"] == "A1"
    assert state["timeline"][0]["speed"] == 4

    assert any("速度補正" in message for _, message, _ in logs)


def test_speed_value_condition_reads_battle_state_slots():
    actor = {"id": "A1", "params": [{"label": "速度", "value": 5}], "states": []}
    context = {
        "room_state": {
            "battle_state": {
                "slots": {
                    "S1": {"actor_id": "A1", "initiative": 7},
                    "S2": {"actor_id": "A1", "initiative": 9},
                    "S3": {"actor_id": "B1", "initiative": 12},
                }
            }
        }
    }

    cond_ok = {"source": "self", "param": "速度値", "operator": "GTE", "value": 9}
    cond_ng = {"source": "self", "param": "速度値", "operator": "GT", "value": 9}

    assert check_condition(cond_ok, actor, None, context=context) is True
    assert check_condition(cond_ng, actor, None, context=context) is False


def test_speed_value_condition_prefers_timeline_for_target():
    actor = {"id": "D1", "params": [{"label": "速度", "value": 6}], "states": []}
    target = {"id": "A1", "params": [{"label": "速度", "value": 9}], "states": []}
    context = {
        "timeline": [
            {"id": "S_A1", "char_id": "A1", "speed": 9},
            {"id": "S_D1", "char_id": "D1", "speed": 6},
        ]
    }
    cond = {"source": "target", "param": "速度値", "operator": "LTE", "value": 4}
    assert check_condition(cond, actor, target, context=context) is False


def test_speed_value_condition_does_not_fire_when_speed_unresolved():
    actor = {"id": "D1", "params": [{"label": "速度", "value": 6}], "states": []}
    target = {"id": "A1", "params": [{"label": "速度", "value": 9}], "states": []}
    cond = {"source": "target", "param": "速度値", "operator": "LTE", "value": 4}
    assert check_condition(cond, actor, target, context={}) is False


def test_apply_speed_mod_buff_defaults_to_next_round_and_stacks_by_delay_bucket():
    char = {
        "id": "A1",
        "name": "ActorA",
        "special_buffs": [
            {"name": "加速", "buff_id": "Bu-11", "count": 1, "delay": 0, "lasting": 1, "is_permanent": False}
        ],
    }

    # default delay=0 request should be normalized to pending(delay=1)
    apply_buff(char, "加速", lasting=1, delay=0, data={"buff_id": "Bu-11"}, count=2)
    # same delay bucket stacks
    apply_buff(char, "加速", lasting=1, delay=0, data={"buff_id": "Bu-11"}, count=3)
    # explicit farther delay creates separate bucket
    apply_buff(char, "加速", lasting=1, delay=2, data={"buff_id": "Bu-11"}, count=4)

    buckets = [b for b in char.get("special_buffs", []) if b.get("buff_id") == "Bu-11"]
    bucket_active = next((b for b in buckets if int(b.get("delay", -1)) == 0), None)
    bucket_d1 = next((b for b in buckets if int(b.get("delay", -1)) == 1), None)
    bucket_d2 = next((b for b in buckets if int(b.get("delay", -1)) == 2), None)

    assert bucket_active is not None
    assert bucket_d1 is not None
    assert bucket_d2 is not None

    assert int(bucket_active.get("count", 0)) == 1
    assert int(bucket_d1.get("count", 0)) == 5
    assert int(bucket_d2.get("count", 0)) == 4
    assert int(bucket_d1.get("lasting", 0)) == 1
    assert bool(bucket_d1.get("is_permanent", False)) is False


def test_speed_modifier_counts_only_active_delay_zero_bucket():
    char = {
        "special_buffs": [
            {"name": "加速", "buff_id": "Bu-11", "count": 3, "delay": 0, "lasting": 1},
            {"name": "加速", "buff_id": "Bu-11", "count": 2, "delay": 1, "lasting": 1},
            {"name": "減速", "buff_id": "Bu-12", "count": 1, "delay": 0, "lasting": 1},
            {"name": "減速", "buff_id": "Bu-12", "count": 5, "delay": 2, "lasting": 1},
        ]
    }

    from plugins.buffs.speed_mod import SpeedModBuff

    # active only: +3 -1 = +2
    assert SpeedModBuff.get_speed_modifier(char) == 2

