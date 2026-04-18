from manager.utils import get_status_value
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
        "special_buffs": [
            {"name": "加速", "buff_id": "Bu-11", "count": 2},  # 加速 +2
            {"name": "減速", "buff_id": "Bu-12", "count": 1},  # 減速 -1
            {"name": "Dummy", "buff_id": "Bu-99", "count": 1},  # unrelated
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

    # 速度12 -> 12//6=2, 補正(+2-1)=+1, 1d6=1 => 速度値 4
    assert slot["initiative"] == 4
    assert slot["speed_stat"] == 12
    assert slot["speed_base"] == 3
    assert slot["speed_modifier"] == 1
    assert slot["speed_roll"] == 1

    # 速度値ロール互換情報
    assert char["speedRoll"] == 1
    assert char["totalSpeed"] == 4
    assert char["hasActed"] is False

    # 加速/減速のみクリアされ、他のバフは残る
    remaining_ids = [b.get("buff_id") for b in char.get("special_buffs", [])]
    assert "Bu-11" not in remaining_ids
    assert "Bu-12" not in remaining_ids
    assert "Bu-99" in remaining_ids

    # 旧timelineも同一スロットIDで再構築される
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
