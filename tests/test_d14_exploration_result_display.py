from types import SimpleNamespace

import pytest

from events import socket_exploration


@pytest.mark.parametrize("difficulty,result", [(8, "SUCCESS"), (9, "FAILURE"), (0, None)])
def test_exploration_status_uses_allowed_markup_and_escapes_user_text(monkeypatch, difficulty, result):
    monkeypatch.setattr(socket_exploration, "request", SimpleNamespace(sid="sid"))
    monkeypatch.setattr(socket_exploration, "is_sid_in_room", lambda *_args: True)
    monkeypatch.setattr(socket_exploration, "get_room_state", lambda _room: {
        "characters": [{"id": "C", "name": '<img src=x onerror="alert(1)">'}],
    })
    monkeypatch.setattr(socket_exploration.random, "randint", lambda *_args: 3)
    logs = []
    monkeypatch.setattr(socket_exploration, "broadcast_log", lambda _room, message, kind: logs.append((message, kind)))
    socket_exploration.handle_exploration_roll({
        "room": "room_t", "char_id": "C", "skill_name": "<strong>test</strong>",
        "skill_level": 2, "dice_count": 2, "difficulty": difficulty,
    })
    message, kind = logs[0]
    assert kind == "dice_roll"
    assert "2d6(6) + Lv2 = 8" in message
    assert "<span" not in message
    assert "<img" not in message and "<strong>test</strong>" not in message
    assert "&lt;img" in message and "&lt;strong&gt;test" in message
    if result:
        assert f"<strong>【{result}】</strong>" in message
    else:
        assert "SUCCESS" not in message and "FAILURE" not in message
