from manager import room_manager


def test_broadcast_log_dedupes_consecutive_identical_bleed_state_change(monkeypatch):
    state = {"logs": [], "_log_seq": 0}
    emitted = []

    monkeypatch.setattr(room_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(room_manager, "save_specific_room_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(room_manager, "_safe_emit", lambda event, payload, **_kwargs: emitted.append((event, payload)))

    line = "[\u51fa\u8840]: \u30c7\u30d0\u30c3\u30b0\u30fb\u30bf\u30ed\u30a6 [\u5473\u65b9 1]: \u51fa\u8840 (3) -> (1)"
    room_manager.broadcast_log("room_t", line, "state-change")
    room_manager.broadcast_log("room_t", line, "state-change")

    assert len(state["logs"]) == 1
    assert len(emitted) == 1
    assert state["logs"][0]["message"] == line


def test_broadcast_log_keeps_non_bleed_duplicates(monkeypatch):
    state = {"logs": [], "_log_seq": 0}
    emitted = []

    monkeypatch.setattr(room_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(room_manager, "save_specific_room_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(room_manager, "_safe_emit", lambda event, payload, **_kwargs: emitted.append((event, payload)))

    line = "[\u7d50\u679c] \u30c7\u30d0\u30c3\u30b0\u30fb\u30bf\u30ed\u30a6 [\u5473\u65b9 1] FP: 994 -> 992"
    room_manager.broadcast_log("room_t", line, "state-change")
    room_manager.broadcast_log("room_t", line, "state-change")

    assert len(state["logs"]) == 2
    assert len(emitted) == 2


def test_update_char_stat_suppress_log_skips_state_change_broadcast(monkeypatch):
    char = {
        "id": "A1",
        "name": "\u653b\u6483\u8005",
        "hp": 20,
        "maxHp": 20,
        "mp": 0,
        "maxMp": 0,
        "states": [{"name": "\u51fa\u8840", "value": 0}],
        "params": [],
    }
    state = {"logs": [], "_log_seq": 0}
    emitted = []

    monkeypatch.setattr(room_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(room_manager, "save_specific_room_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(room_manager, "_safe_emit", lambda event, payload, **_kwargs: emitted.append((event, payload)))

    room_manager._update_char_stat("room_t", char, "\u51fa\u8840", 2, username="[Passive]", suppress_log=True)

    assert len(state["logs"]) == 0
    assert any(event == "char_stat_updated" for event, _payload in emitted)
