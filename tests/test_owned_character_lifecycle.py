"""計画36 end-to-end通しテスト。

Phase 1〜5個別のテスト（test_owned_characters_api / test_chara_creator_route /
test_add_character_owned_character / test_reflect_session_results /
test_owned_character_growth）は各機能を単体で検証している。本ファイルは
「作成 → ルーム投入 → セッション内変化 → 成果反映 → 成長 → 一貫性確認 → 削除」
という一連の流れを1本の物語として通し、フェーズ間の結合部分（owned_character_id
の受け渡し、exp_total/growth_logの整合、他人からの隔離）にリグレッションが
無いことを確認する。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

from types import SimpleNamespace

import pytest

from app import create_app
from extensions import db
import extensions
from models import User, OwnedCharacter
from routes import owned_characters as oc
from events import socket_char


FAKE_SKILLS = {
    "Ps-01": {"取得コスト": "1", "チャットパレット": "1d6 【Ps-01 斬撃】"},
    "B-01": {"取得コスト": "2", "チャットパレット": "0+0 【B-01 テスト魔法】"},
}


@pytest.fixture(autouse=True)
def patch_skill_data(monkeypatch):
    monkeypatch.setattr(extensions, "all_skill_data", FAKE_SKILLS)
    monkeypatch.setattr(oc, "all_skill_data", FAKE_SKILLS)
    monkeypatch.setattr(socket_char, "all_skill_data", FAKE_SKILLS)
    yield


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "owned_character_lifecycle.db"
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
        for uid in ("owner", "gm_user", "stranger"):
            db.session.add(User(id=uid, name=uid))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def _login(client, user_id):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["username"] = user_id
        s["attribute"] = "Player"
        s["auth_version"] = 1


def _sample_creation_payload():
    return {
        "kind": "character",
        "data": {
            "name": "通しテスト太郎",
            "status": [{"label": "HP", "value": 20, "max": 20}],
            "params": [
                {"label": "経験", "value": "6"},
                {"label": "シナリオ経験", "value": "2"},
                {"label": "筋力", "value": "3"},
            ],
            "commands": "",
            "SPassive": [],
            "inventory": {},
        },
    }


def _make_emit_capture():
    emits = []
    return emits, lambda event, payload=None, to=None: emits.append((event, payload or {}, to))


def _patch_socket_char(monkeypatch, state, user_id, attribute="Player"):
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


def test_full_owned_character_lifecycle(client, app_ctx, monkeypatch):
    # --- 1. 作成（CharaCreatorの保存ボタン相当） ---
    _login(client, "owner")
    resp = client.post("/api/owned_characters", json=_sample_creation_payload())
    assert resp.status_code == 201
    character = resp.get_json()["character"]
    owned_id = character["id"]
    # 経験(6)+シナリオ経験(2) = 8 で exp_total が初期化されること
    assert character["exp_total"] == 8
    assert character["remaining_exp"] == 8
    assert character["skill_exp_budget"] == 8

    # 他人からは見えない・触れない
    _login(client, "stranger")
    assert client.get(f"/api/owned_characters/{owned_id}").status_code == 404
    assert client.put(f"/api/owned_characters/{owned_id}", json=_sample_creation_payload()).status_code == 404
    assert client.delete(f"/api/owned_characters/{owned_id}").status_code == 404
    _login(client, "owner")

    # --- 2. ルームへの投入（持ちキャラから選ぶ） ---
    with app_ctx.app_context():
        state = {"characters": [], "presets": {}, "play_mode": "normal",
                 "battle_state": {"behavior_runtime": {}}}
        char_data = {
            "name": "通しテスト太郎", "type": "ally",
            "status": [{"label": "HP", "value": 20, "max": 20}],
            "params": [{"label": "筋力", "value": "3"}],
            "commands": "",
        }
        emits = _patch_socket_char(monkeypatch, state, user_id="owner")
        socket_char.handle_add_character({
            "room": "room_t", "charData": char_data, "ownedCharacterId": owned_id,
        })
        assert not any(e[0] == "error" for e in emits)
        room_char = state["characters"][0]
        assert room_char["owned_character_id"] == owned_id
        # handle_add_character はサーバー側で独自の char_id を採番するため、
        # 以降の反映呼び出しはここで生成された実際のIDを使う。
        room_char_id = room_char["id"]

        # --- 3. セッション内でルーム側キャラが変化しても持ちキャラ本体は無事 ---
        room_char["status"][0]["value"] = 1  # HPが減った、を模す
        owned_after_damage = OwnedCharacter.query.get(owned_id)
        assert owned_after_damage.data["status"][0]["value"] == 20

        # --- 4. 成果反映（GM操作） ---
        emits = _patch_socket_char(monkeypatch, state, user_id="gm_user", attribute="GM")
        socket_char.handle_reflect_session_results({
            "room": "room_t", "char_id": room_char_id,
            "exp_gain": 3, "items": {"item-heal": 2},
        })
        result = next(p for (ev, p, _to) in emits if ev == "reflect_session_results_result")
        assert result["skipped"] is False
        assert result["exp_gain"] == 3
        assert result["items_gain"] == {"item-heal": 2}

        # 二重反映は防止される
        emits2 = _patch_socket_char(monkeypatch, state, user_id="gm_user", attribute="GM")
        socket_char.handle_reflect_session_results({
            "room": "room_t", "char_id": room_char_id, "exp_gain": 100,
        })
        result2 = next(p for (ev, p, _to) in emits2 if ev == "reflect_session_results_result")
        assert result2["skipped"] is True
        assert result2["reason"] == "already_reflected"

    # ここまでの反映をAPI経由で確認: exp_total = 8 + 3 = 11
    resp = client.get(f"/api/owned_characters/{owned_id}")
    body = resp.get_json()["character"]
    assert body["exp_total"] == 11
    assert body["data"]["inventory"]["item-heal"] == 2
    assert len(body["growth_log"]) == 1
    assert body["growth_log"][0]["kind"] == "reflect_session_results"
    assert body["remaining_exp"] == 11  # まだ何もスキル/成長を消費していない

    # --- 5. 成長画面でスキル追加とパラメータ上昇 ---
    resp = client.post(f"/api/owned_characters/{owned_id}/growth", json={
        "add_skill_ids": ["Ps-01"], "param_increases": {"筋力": 2},
    })
    assert resp.status_code == 200
    grown = resp.get_json()["character"]
    # コスト: Ps-01(1) + 筋力+2(2) = 3。 remaining = 11 - 3 = 8
    assert grown["remaining_exp"] == 8
    assert grown["exp_total"] == 11  # exp_total自体は不変
    assert "【Ps-01" in grown["data"]["commands"]
    strength = next(p for p in grown["data"]["params"] if p["label"] == "筋力")
    assert strength["value"] == "5"  # 3 + 2
    assert len(grown["growth_log"]) == 2
    assert grown["growth_log"][1]["kind"] == "growth"

    # skill_exp_budget はパラメータ成長消費分(2)だけ引かれ、スキルコストは含まない
    assert grown["skill_exp_budget"] == 9  # 11 - 2

    # --- 6. 予算超過は拒否され、状態は変化しない ---
    resp = client.post(f"/api/owned_characters/{owned_id}/growth", json={
        "add_skill_ids": ["B-01"], "param_increases": {"生命力": 100},
    })
    assert resp.status_code == 400
    unchanged = client.get(f"/api/owned_characters/{owned_id}").get_json()["character"]
    assert unchanged["remaining_exp"] == 8
    assert len(unchanged["growth_log"]) == 2  # 拒否分は記録されない

    # --- 7. 他人はこのキャラを成長させられない ---
    _login(client, "stranger")
    resp = client.post(f"/api/owned_characters/{owned_id}/growth", json={"add_skill_ids": ["Ps-01"]})
    assert resp.status_code == 404
    _login(client, "owner")

    # --- 8. 削除（論理削除） ---
    resp = client.delete(f"/api/owned_characters/{owned_id}")
    assert resp.status_code == 200
    assert client.get("/api/owned_characters").get_json()["characters"] == []

    with app_ctx.app_context():
        row = OwnedCharacter.query.get(owned_id)
        assert row is not None
        assert row.deleted_at is not None
        # 削除後も過去の growth_log は保全されている（監査目的）
        assert len(row.growth_log) == 2
