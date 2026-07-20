"""計画36 Phase 3: request_add_character の持ちキャラ投入対応の回帰テスト。

投入導線そのもの（`GET /api/owned_characters/<id>` → クライアント側正規化 →
`request_add_character`）は、サーバ側では「owned_character_id の所有権確認と
タグ付け」だけを担う設計（events/socket_char.py::_resolve_owned_character_tag）。
ここではその境界を検証する。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import copy
from types import SimpleNamespace

import pytest

from app import create_app
from extensions import db
from models import User, OwnedCharacter
from events import socket_char


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "add_character_owned.db"
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
        db.session.add(User(id="stranger", name="stranger"))
        owned = OwnedCharacter(
            id="owned_1",
            user_id="owner",
            name="投入テストキャラ",
            data={"name": "投入テストキャラ", "status": [{"label": "HP", "value": 20, "max": 20}]},
            exp_total=0,
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


def _base_state():
    return {"characters": [], "presets": {}, "battle_state": {"behavior_runtime": {}}}


def test_owned_character_id_is_stamped_when_owner_matches(app_ctx, monkeypatch):
    with app_ctx.app_context():
        state = _base_state()
        emits = _patch_char(monkeypatch, state, user_id="owner")

        socket_char.handle_add_character({
            "room": "room_t",
            "charData": {"name": "投入テストキャラ", "type": "ally"},
            "ownedCharacterId": "owned_1",
        })

        assert not any(e[0] == "error" for e in emits)
        assert len(state["characters"]) == 1
        assert state["characters"][0]["owned_character_id"] == "owned_1"


def test_owned_character_id_is_ignored_for_non_owner(app_ctx, monkeypatch):
    with app_ctx.app_context():
        state = _base_state()
        emits = _patch_char(monkeypatch, state, user_id="stranger")

        socket_char.handle_add_character({
            "room": "room_t",
            "charData": {"name": "なりすまし", "type": "ally"},
            "ownedCharacterId": "owned_1",
        })

        # 追加自体は成功するが、他人の持ちキャラIDはタグ付けされない。
        assert not any(e[0] == "error" for e in emits)
        assert len(state["characters"]) == 1
        assert "owned_character_id" not in state["characters"][0]


def test_owned_character_id_is_ignored_when_missing(app_ctx, monkeypatch):
    with app_ctx.app_context():
        state = _base_state()
        _patch_char(monkeypatch, state, user_id="owner")

        socket_char.handle_add_character({
            "room": "room_t",
            "charData": {"name": "IDなし", "type": "ally"},
            "ownedCharacterId": "does-not-exist",
        })

        assert "owned_character_id" not in state["characters"][0]


def test_investing_copy_does_not_mutate_owned_character_data(app_ctx, monkeypatch):
    """投入時にクライアントが持ち込む charData は、GET経由(=JSON往復)で得た
    OwnedCharacter.data のコピーである、という前提を模してテストする。
    ルーム側キャラを書き換えても DB 上の持ちキャラ本体には影響しない。
    """
    with app_ctx.app_context():
        owned = OwnedCharacter.query.get("owned_1")
        # クライアントが GET → JSON化 → 復元する過程を模した独立コピー
        char_data = copy.deepcopy(owned.to_dict()["data"])
        char_data["type"] = "ally"

        state = _base_state()
        _patch_char(monkeypatch, state, user_id="owner")

        socket_char.handle_add_character({
            "room": "room_t",
            "charData": char_data,
            "ownedCharacterId": "owned_1",
        })

        # ルーム内キャラを書き換える（HPが減った、等を模す）
        state["characters"][0]["status"][0]["value"] = 1

        db.session.expire_all()
        owned_after = OwnedCharacter.query.get("owned_1")
        assert owned_after.data["status"][0]["value"] == 20


def test_player_room_entry_rebuilds_tags_from_trusted_fields(app_ctx, monkeypatch):
    with app_ctx.app_context():
        monkeypatch.setattr(
            socket_char.radiance_loader,
            "load_skills",
            lambda force_refresh=False: {
                "S-TAG": {"id": "S-TAG", "cost": 1, "granted_tag_ids": ["特性:機械知識"]}
            },
        )
        state = _base_state()
        _patch_char(monkeypatch, state, user_id="owner")

        socket_char.handle_add_character({
            "room": "room_t",
            "charData": {
                "name": "投入テストキャラ",
                "type": "ally",
                "characterType": "player",
                "params": [
                    {"label": "出身", "value": "10"},
                    {"label": "通過点", "value": "1"},
                ],
                "SPassive": ["S-TAG"],
                "tag_ids": ["種別:瓦礫"],
                "disabled_tag_ids": ["種別:瓦礫"],
            },
        })

        char = state["characters"][0]
        assert char["tag_ids"] == ["出身:シンシア", "特性:機械知識"]
        assert char["disabled_tag_ids"] == []


def test_gm_scenario_room_entry_preserves_free_tag_state(app_ctx, monkeypatch):
    with app_ctx.app_context():
        state = _base_state()
        _patch_char(monkeypatch, state, user_id="owner", attribute="GM")

        socket_char.handle_add_character({
            "room": "room_t",
            "charData": {
                "name": "瓦礫",
                "type": "enemy",
                "characterType": "scenario",
                "isNPC": True,
                "tag_ids": ["種別:瓦礫", "機械"],
                "disabled_tag_ids": ["機械"],
            },
        })

        char = state["characters"][0]
        assert char["tag_ids"] == ["種別:瓦礫", "機械"]
        assert char["disabled_tag_ids"] == ["機械"]
