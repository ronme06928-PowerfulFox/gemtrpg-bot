"""Phase 0: モバイル版の開発停止に伴う /mobile 導線の停止テスト。

PC Web版中心の方針のため、/mobile と mobile アセットの直接読み出しを
404 で停止する。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "mobile.db"
    test_app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    return test_app.test_client()


def test_mobile_entry_suspended(client):
    resp = client.get("/mobile")
    assert resp.status_code == 404
    assert "停止" in resp.get_data(as_text=True)


def test_mobile_asset_suspended(client):
    resp = client.get("/mobile/js/portal.js")
    assert resp.status_code == 404


def test_pc_index_still_served(client):
    # PC版のトップは引き続き配信される。
    resp = client.get("/")
    assert resp.status_code == 200
