"""Phase 0: Render/ローカルのDB選択 fail-closed ガードのテスト。

- ローカルでは DATABASE_URL を無視して SQLite を使う。
- Render では DATABASE_URL 未設定なら起動失敗させる。
- Render では非PostgreSQLのURLを拒否する。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

import app as app_module


def test_local_ignores_database_url(monkeypatch):
    monkeypatch.setattr(app_module, "IS_RENDER", False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://should/be/ignored")
    assert app_module._get_database_uri() == "sqlite:///gemtrpg.db"


def test_render_requires_database_url(monkeypatch):
    monkeypatch.setattr(app_module, "IS_RENDER", True)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        app_module._get_database_uri()


def test_render_rejects_sqlite_url(monkeypatch):
    monkeypatch.setattr(app_module, "IS_RENDER", True)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///gemtrpg.db")
    with pytest.raises(RuntimeError):
        app_module._get_database_uri()


def test_render_rejects_empty_database_url(monkeypatch):
    monkeypatch.setattr(app_module, "IS_RENDER", True)
    monkeypatch.setenv("DATABASE_URL", "   ")
    with pytest.raises(RuntimeError):
        app_module._get_database_uri()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@host:5432/db",
        "postgres://user:pass@host/db",
        "postgresql+psycopg2://user:pass@host/db",
    ],
)
def test_render_accepts_postgres_url(monkeypatch, url):
    monkeypatch.setattr(app_module, "IS_RENDER", True)
    monkeypatch.setenv("DATABASE_URL", url)
    assert app_module._get_database_uri() == url
