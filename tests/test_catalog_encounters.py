import os
from types import SimpleNamespace

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from events import socket_char
from extensions import active_room_states, db, user_sids
from manager import encounters
from manager.buff_apply import apply_buff
from models import CatalogEncounter, User


@pytest.fixture
def room(monkeypatch):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "SQLALCHEMY_ENGINE_OPTIONS": {}},
                     run_startup=False, register_sockets=False)
    tasks = []
    monkeypatch.setattr(encounters.socketio, "start_background_task", lambda fn: tasks.append(fn))
    monkeypatch.setattr(encounters.socketio, "sleep", lambda _: None)
    for sid, user_id, name in [("gm", "gm", "test"), ("player", "player", "test"),
                               ("second-tab", "player", "test"), ("away", "away", "other"),
                               ("anonymous", None, "test")]:
        monkeypatch.setitem(user_sids, sid, {"user_id": user_id, "room": name})
    state = {"characters": [], "character_owners": {}}
    monkeypatch.setitem(active_room_states, "test", state)
    with app.app_context():
        db.create_all()
        db.session.add_all(User(id=user_id, name=user_id) for user_id in ("gm", "player", "away"))
        db.session.commit()
        yield state, tasks
        db.session.remove()
        db.engine.dispose()


def test_arrival_reveal_and_buff_are_batched_for_connected_users_only(room):
    state, tasks = room
    enemy = {"id": "enemy", "type": "enemy", "source_unit_id": "U-001",
             "SPassive": ["Pa-03", "S-01"], "commands": "1d6 【E-01 技】\n1d6 【Ps-01 技】"}
    ally = {"id": "ally", "type": "ally", "SPassive": ["Pa-02"], "hidden_skills": ["Ps-02"]}
    state["characters"] = [enemy, ally]
    for char in state["characters"]:
        encounters.hide_enemy_skills(char)
        encounters.record_arrivals("test", [char])
    assert enemy["hidden_skills"] == ["E-01", "Ps-01"]
    assert ally["hidden_skills"] == ["Ps-02"]
    assert encounters.reveal_enemy_skill("test", enemy, "Ps-01")
    assert enemy["hidden_skills"] == ["E-01"]
    apply_buff({**ally}, "試算用", 1, 0, data={"buff_id": "Bu-99"})
    apply_buff(ally, "試験用", 1, 0, data={"data": {"buff_id": "Bu-98"}})
    assert CatalogEncounter.query.count() == 0
    assert len(tasks) == 1
    tasks.pop()()
    expected = {("unit", "U-001"), ("passive", "Pa-03"), ("skill", "Ps-01"), ("buff", "Bu-98")}
    seen = {(r.user_id, r.kind, r.entry_id): (r.first_seen_at, r.room_name) for r in CatalogEncounter.query.all()}
    assert set(seen) == {(user, kind, entry_id) for user in ("gm", "player") for kind, entry_id in expected}
    # A later encounter from another room must preserve the original row.
    user_sids["gm"]["room"] = "other"
    encounters.record("other", [("skill", "Ps-01")])
    tasks.pop()()
    assert {(r.user_id, r.kind, r.entry_id): (r.first_seen_at, r.room_name)
            for r in CatalogEncounter.query.all() if r.user_id != "away"} == seen


def test_manual_add_and_gm_unhide_use_the_actual_character(room, monkeypatch):
    state, tasks = room
    monkeypatch.setattr(socket_char, "request", SimpleNamespace(sid="gm"))
    monkeypatch.setattr(socket_char, "session", {"user_id": "gm"})
    monkeypatch.setattr(socket_char, "_require_in_room", lambda _: True)
    monkeypatch.setattr(socket_char, "get_user_info_from_sid", lambda _: {"username": "gm", "attribute": "GM"})
    for fn in ("set_character_owner", "broadcast_log", "broadcast_state_update", "save_specific_room_state"):
        monkeypatch.setattr(socket_char, fn, lambda *args, **kwargs: None)
    enemy_data = {"name": "敵", "commands": "1d6 【E-01 技】", "SPassive": ["Pa-01"],
                  "source_unit_id": "U-999"}
    socket_char.handle_add_character({"room": "test", "charData": enemy_data})
    socket_char.handle_add_character({"room": "test", "charData": {**enemy_data, "type": "ally", "hidden_skills": []}})
    enemy, ally = state["characters"]
    assert enemy["type"] == "enemy" and enemy["hidden_skills"] == ["E-01"]
    assert ally["hidden_skills"] == []
    socket_char.handle_state_update({"room": "test", "charId": enemy["id"], "changes": {"hidden_skills": []}})
    tasks.pop()()
    assert {(r.kind, r.entry_id) for r in CatalogEncounter.query.all()} == {("passive", "Pa-01"), ("skill", "E-01")}
