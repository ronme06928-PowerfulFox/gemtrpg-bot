"""計画36 Phase 1: 持ちキャラCRUD APIの回帰テスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db
from models import User, OwnedCharacter
import routes.owned_characters as owned_routes
from routes.owned_characters import OWNED_CHARACTER_LIMIT


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "owned_characters.db"
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
        for uid in ("owner", "stranger"):
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


def _sample_payload(name="テストキャラ"):
    return {
        "kind": "character",
        "data": {
            "name": name,
            "status": [{"label": "HP", "value": 20, "max": 20}],
            "params": [{"label": "筋力", "value": 3}],
            "commands": "2d6 【殴打】",
            "SPassive": [],
            "inventory": {},
        },
    }


def test_requires_login(client):
    resp = client.get("/api/owned_characters")
    assert resp.status_code == 401


def test_create_and_list(client):
    _login(client, "owner")
    resp = client.post("/api/owned_characters", json=_sample_payload())
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["character"]["name"] == "テストキャラ"
    assert body["character"]["exp_total"] == 0
    assert body["character"]["growth_log"] == []

    resp = client.get("/api/owned_characters")
    assert resp.status_code == 200
    characters = resp.get_json()["characters"]
    assert len(characters) == 1
    assert characters[0]["name"] == "テストキャラ"


def test_create_rejects_missing_name(client):
    _login(client, "owner")
    resp = client.post("/api/owned_characters", json={"data": {"status": []}})
    assert resp.status_code == 400


def test_create_rejects_non_object_body(client):
    _login(client, "owner")
    resp = client.post("/api/owned_characters", data="not json", content_type="application/json")
    assert resp.status_code == 400


def test_update_owned_character(client):
    _login(client, "owner")
    created = client.post("/api/owned_characters", json=_sample_payload()).get_json()["character"]

    resp = client.put(
        f"/api/owned_characters/{created['id']}",
        json=_sample_payload(name="改名後"),
    )
    assert resp.status_code == 200
    assert resp.get_json()["character"]["name"] == "改名後"

    resp = client.get("/api/owned_characters")
    characters = resp.get_json()["characters"]
    assert characters[0]["name"] == "改名後"


def test_player_create_rebuilds_tags_and_discards_disabled_tags(client, monkeypatch):
    monkeypatch.setattr(
        owned_routes.radiance_loader,
        "load_skills",
        lambda force_refresh=False: {
            "S-TAG": {"id": "S-TAG", "cost": 1, "granted_tag_ids": ["特性:機械知識"]}
        },
    )
    _login(client, "owner")
    payload = _sample_payload()
    payload["data"].update({
        "characterType": "player",
        "params": [
            {"label": "出身", "value": "1"},
            {"label": "ボーナス", "value": "2"},
            {"label": "通過点", "value": "1"},
        ],
        "SPassive": ["S-TAG"],
        "tag_ids": ["種別:瓦礫"],
        "disabled_tag_ids": ["種別:瓦礫"],
    })

    resp = client.post("/api/owned_characters", json=payload)

    assert resp.status_code == 201
    data = resp.get_json()["character"]["data"]
    assert data["tag_ids"] == [
        "出身:ヨキューク・ツォー",
        "出身:アーク・ジェムリア",
        "特性:機械知識",
    ]
    assert data["disabled_tag_ids"] == []


def test_player_create_rejects_radiance_overspend(client, monkeypatch):
    monkeypatch.setattr(
        owned_routes.radiance_loader,
        "load_skills",
        lambda force_refresh=False: {"S-TAG": {"id": "S-TAG", "cost": 2}},
    )
    _login(client, "owner")
    payload = _sample_payload()
    payload["data"].update({
        "params": [{"label": "通過点", "value": "1"}],
        "SPassive": ["S-TAG"],
    })

    resp = client.post("/api/owned_characters", json=payload)

    assert resp.status_code == 400
    assert "通過点が不足" in resp.get_json()["error"]


def test_gm_scenario_create_preserves_free_and_disabled_tags(client):
    _login(client, "owner")
    with client.session_transaction() as session_data:
        session_data["attribute"] = "GM"
    payload = _sample_payload()
    payload["data"].update({
        "characterType": "scenario",
        "isNPC": True,
        "tag_ids": [" 種別:瓦礫 ", "機械"],
        "disabled_tag_ids": ["機械", "未知"],
    })

    resp = client.post("/api/owned_characters", json=payload)

    assert resp.status_code == 201
    character = resp.get_json()["character"]
    data = character["data"]
    assert data["tag_ids"] == ["種別:瓦礫", "機械"]
    assert data["disabled_tag_ids"] == ["機械"]

    with client.session_transaction() as session_data:
        session_data["attribute"] = "Player"
    fetched = client.get(f"/api/owned_characters/{character['id']}").get_json()["character"]["data"]
    assert fetched["tag_ids"] == ["種別:瓦礫", "機械"]
    assert fetched["disabled_tag_ids"] == ["機械"]


def test_gm_scenario_create_rejects_tag_over_25_characters(client):
    _login(client, "owner")
    with client.session_transaction() as session_data:
        session_data["attribute"] = "GM"
    payload = _sample_payload()
    payload["data"].update({
        "characterType": "scenario",
        "isNPC": True,
        "tag_ids": ["あ" * 26],
    })

    resp = client.post("/api/owned_characters", json=payload)

    assert resp.status_code == 400
    assert "25文字以内" in resp.get_json()["error"]


def test_delete_owned_character_is_soft_delete(client, app_ctx):
    _login(client, "owner")
    created = client.post("/api/owned_characters", json=_sample_payload()).get_json()["character"]

    resp = client.delete(f"/api/owned_characters/{created['id']}")
    assert resp.status_code == 200

    resp = client.get("/api/owned_characters")
    assert resp.get_json()["characters"] == []

    with app_ctx.app_context():
        row = OwnedCharacter.query.get(created["id"])
        assert row is not None
        assert row.deleted_at is not None


def test_cross_user_isolation(client):
    _login(client, "owner")
    created = client.post("/api/owned_characters", json=_sample_payload()).get_json()["character"]

    _login(client, "stranger")
    resp = client.get("/api/owned_characters")
    assert resp.get_json()["characters"] == []

    resp = client.put(f"/api/owned_characters/{created['id']}", json=_sample_payload(name="乗っ取り"))
    assert resp.status_code == 404

    resp = client.delete(f"/api/owned_characters/{created['id']}")
    assert resp.status_code == 404

    _login(client, "owner")
    resp = client.get("/api/owned_characters")
    assert resp.get_json()["characters"][0]["name"] == "テストキャラ"


def test_owned_character_limit(client):
    _login(client, "owner")
    for i in range(OWNED_CHARACTER_LIMIT):
        resp = client.post("/api/owned_characters", json=_sample_payload(name=f"キャラ{i}"))
        assert resp.status_code == 201

    resp = client.post("/api/owned_characters", json=_sample_payload(name="上限超え"))
    assert resp.status_code == 400


def test_get_single_owned_character(client):
    _login(client, "owner")
    created = client.post("/api/owned_characters", json=_sample_payload()).get_json()["character"]

    resp = client.get(f"/api/owned_characters/{created['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["character"]["name"] == "テストキャラ"


def test_get_single_owned_character_cross_user_isolation(client):
    _login(client, "owner")
    created = client.post("/api/owned_characters", json=_sample_payload()).get_json()["character"]

    _login(client, "stranger")
    resp = client.get(f"/api/owned_characters/{created['id']}")
    assert resp.status_code == 404


def test_get_single_owned_character_not_found(client):
    _login(client, "owner")
    resp = client.get("/api/owned_characters/does-not-exist")
    assert resp.status_code == 404


def test_deleted_character_does_not_count_toward_limit(client):
    _login(client, "owner")
    created = client.post("/api/owned_characters", json=_sample_payload()).get_json()["character"]
    client.delete(f"/api/owned_characters/{created['id']}")

    for i in range(OWNED_CHARACTER_LIMIT):
        resp = client.post("/api/owned_characters", json=_sample_payload(name=f"キャラ{i}"))
        assert resp.status_code == 201
