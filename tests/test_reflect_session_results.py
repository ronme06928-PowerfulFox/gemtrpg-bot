"""計画36 Phase 4: request_reflect_session_results の回帰テスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

from types import SimpleNamespace

import pytest

from app import create_app
from extensions import db
from models import User, OwnedCharacter
from events import socket_char


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "reflect_results.db"
    app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    with app.app_context():
        db.create_all()
        db.session.add(User(id="owner", name="owner"))
        db.session.add(User(id="other_player", name="other_player"))
        owned = OwnedCharacter(
            id="owned_1",
            user_id="owner",
            name="成果反映テストキャラ",
            data={"name": "成果反映テストキャラ", "inventory": {"item-heal": 1}},
            exp_total=10,
            growth_log=[],
        )
        db.session.add(owned)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _make_emit_capture():
    emits = []
    return emits, lambda event, payload=None, to=None: emits.append((event, payload or {}, to))


def _patch_char(monkeypatch, state, user_id, attribute="Player"):
    emits, capture = _make_emit_capture()
    monkeypatch.setattr(socket_char, "request", SimpleNamespace(sid="sid_t"))
    monkeypatch.setattr(socket_char, "is_sid_in_room", lambda _sid, _room: True)
    monkeypatch.setattr(socket_char, "get_room_state", lambda _r: state)
    monkeypatch.setattr(socket_char, "save_specific_room_state", lambda _r: None)
    monkeypatch.setattr(socket_char, "broadcast_state_update", lambda *_a, **_kw: None)
    monkeypatch.setattr(socket_char, "broadcast_log", lambda *_a, **_kw: None)
    monkeypatch.setattr(socket_char, "get_user_info_from_sid",
                         lambda _sid: {"username": "tester", "attribute": attribute})
    monkeypatch.setattr(socket_char, "session", {"user_id": user_id})
    monkeypatch.setattr(socket_char, "emit", capture)
    monkeypatch.setattr(socket_char.socketio, "emit",
                         lambda event, payload=None, to=None: emits.append((event, payload or {}, to)))
    return emits


def _room_char(owned_character_id="owned_1", owner_id="owner"):
    return {
        "id": "char_1", "name": "成果反映テストキャラ", "type": "ally",
        "owner_id": owner_id, "owned_character_id": owned_character_id,
        "flags": {},
    }


def _state_with_char(char, play_mode="normal"):
    return {"characters": [char], "presets": {}, "play_mode": play_mode,
            "battle_state": {"behavior_runtime": {}}}


def test_reflects_exp_and_items_for_owner(app_ctx, monkeypatch):
    with app_ctx.app_context():
        char = _room_char()
        state = _state_with_char(char)
        emits = _patch_char(monkeypatch, state, user_id="owner")

        socket_char.handle_reflect_session_results({
            "room": "r1", "char_id": "char_1", "exp_gain": 5,
            "items": {"item-heal": 2},
        })

        assert not any(e[0] == "error" for e in emits)
        result = next(p for (ev, p, _to) in emits if ev == "reflect_session_results_result")
        assert result["skipped"] is False
        assert result["exp_gain"] == 5
        assert result["items_gain"] == {"item-heal": 2}

        owned = OwnedCharacter.query.get("owned_1")
        assert owned.exp_total == 15
        assert owned.data["inventory"]["item-heal"] == 3
        assert len(owned.growth_log) == 1
        assert char["flags"]["results_reflected"] is True


def test_gm_can_reflect_on_behalf_of_owner(app_ctx, monkeypatch):
    with app_ctx.app_context():
        char = _room_char()
        state = _state_with_char(char)
        emits = _patch_char(monkeypatch, state, user_id="other_player", attribute="GM")

        socket_char.handle_reflect_session_results({
            "room": "r1", "char_id": "char_1", "exp_gain": 3,
        })

        assert not any(e[0] == "error" for e in emits)
        owned = OwnedCharacter.query.get("owned_1")
        assert owned.exp_total == 13


def test_non_owner_non_gm_is_rejected(app_ctx, monkeypatch):
    with app_ctx.app_context():
        char = _room_char()
        state = _state_with_char(char)
        emits = _patch_char(monkeypatch, state, user_id="other_player", attribute="Player")

        socket_char.handle_reflect_session_results({
            "room": "r1", "char_id": "char_1", "exp_gain": 5,
        })

        assert any(e[0] == "error" for e in emits)
        owned = OwnedCharacter.query.get("owned_1")
        assert owned.exp_total == 10  # unchanged


def test_double_invocation_is_idempotent(app_ctx, monkeypatch):
    with app_ctx.app_context():
        char = _room_char()
        state = _state_with_char(char)
        emits = _patch_char(monkeypatch, state, user_id="owner")

        socket_char.handle_reflect_session_results({
            "room": "r1", "char_id": "char_1", "exp_gain": 5,
        })
        socket_char.handle_reflect_session_results({
            "room": "r1", "char_id": "char_1", "exp_gain": 5,
        })

        owned = OwnedCharacter.query.get("owned_1")
        assert owned.exp_total == 15  # only reflected once, not 20
        assert len(owned.growth_log) == 1

        results = [p for (ev, p, _to) in emits if ev == "reflect_session_results_result"]
        assert results[0]["skipped"] is False
        assert results[1]["skipped"] is True
        assert results[1]["reason"] == "already_reflected"


def test_character_without_owned_character_id_is_skipped(app_ctx, monkeypatch):
    with app_ctx.app_context():
        char = _room_char(owned_character_id=None)
        del char["owned_character_id"]
        state = _state_with_char(char)
        emits = _patch_char(monkeypatch, state, user_id="owner")

        socket_char.handle_reflect_session_results({
            "room": "r1", "char_id": "char_1", "exp_gain": 5,
        })

        result = next(p for (ev, p, _to) in emits if ev == "reflect_session_results_result")
        assert result["skipped"] is True
        assert result["reason"] == "not_owned_character"

        owned = OwnedCharacter.query.get("owned_1")
        assert owned.exp_total == 10  # unchanged


def test_hollow_room_excludes_items_but_reflects_exp(app_ctx, monkeypatch):
    with app_ctx.app_context():
        char = _room_char()
        state = _state_with_char(char, play_mode="hollow")
        emits = _patch_char(monkeypatch, state, user_id="owner")

        socket_char.handle_reflect_session_results({
            "room": "r1", "char_id": "char_1", "exp_gain": 7,
            "items": {"item-heal": 2},
        })

        result = next(p for (ev, p, _to) in emits if ev == "reflect_session_results_result")
        assert result["skipped"] is False
        assert result["items_gain"] == {}

        owned = OwnedCharacter.query.get("owned_1")
        assert owned.exp_total == 17
        assert owned.data["inventory"]["item-heal"] == 1  # unchanged (no items reflected)
