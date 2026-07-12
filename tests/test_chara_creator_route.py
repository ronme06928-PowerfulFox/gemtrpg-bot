"""計画36 Phase 2: キャラ作成ツール配信ルートの回帰テスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "chara_creator_route.db"
    app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    yield app


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def test_chara_creator_route_serves_html_without_login(client):
    # 最小統合方針: 単体ツールとしての利用は未ログインでも可能（保存APIのみ要ログイン）。
    resp = client.get("/chara_creator")
    assert resp.status_code == 200
    assert b"text/html" in resp.headers.get("Content-Type", "").encode()
    body = resp.get_data(as_text=True)
    assert "account-save-btn" in body
    assert "saveToAccount" in body
    assert "applyCharacterJsonToForm" in body


def test_chara_creator_route_not_shadowed_by_static_catch_all(client):
    resp = client.get("/chara_creator")
    assert resp.status_code == 200
    # 静的ファイル配信のcatch-all( /<path:filename> )ではなく専用ルートが応答すること。
    assert "GEMDICEBOT_CharaCreator" in resp.get_data(as_text=True) or "キャラクター" in resp.get_data(as_text=True)
