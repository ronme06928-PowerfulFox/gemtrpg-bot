from manager.battle import common_manager


def test_process_full_round_end_ignores_summon_locked_actor(monkeypatch):
    state = {
        "round": 1,
        "is_round_ended": False,
        "characters": [
            {
                "id": "a1",
                "name": "Ally",
                "type": "ally",
                "hp": 20,
                "x": 0,
                "y": 0,
                "hasActed": True,
                "is_escaped": False,
                "states": [],
                "special_buffs": [],
            },
            {
                "id": "sm1",
                "name": "鉄の小蜘蛛",
                "type": "ally",
                "hp": 30,
                "x": 1,
                "y": 0,
                "hasActed": False,
                "is_escaped": False,
                "is_summoned": True,
                "can_act_from_round": 2,
                "states": [],
                "special_buffs": [],
            },
        ],
        "timeline": [],
        "battle_state": {},
    }

    emitted = []

    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_manager, "save_specific_room_state", lambda _room: None)
    monkeypatch.setattr(common_manager, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "broadcast_state_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "emit", lambda event, payload=None, **_kwargs: emitted.append((event, payload)))
    monkeypatch.setattr(common_manager, "process_summon_round_end", lambda _state, room=None: [])
    monkeypatch.setattr(common_manager, "ensure_battle_state_vNext", lambda *_args, **_kwargs: {"resolve": {}})

    common_manager.process_full_round_end("room_t", "tester")

    assert state["is_round_ended"] is True
    assert not any("まだ行動していないキャラクターがいます" in str((p or {}).get("message", "")) for _e, p in emitted)
