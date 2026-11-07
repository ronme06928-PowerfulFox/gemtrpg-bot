"""Phase 0: Render/ローカルのDB選択 fail-closed ガードのテスト。

- ローカルでは DATABASE_URL を無視して SQLite を使う。
- Render では DATABASE_URL 未設定なら起動失敗させる。
- Render では非PostgreSQLのURLを拒否する。
- Render ではPostgreSQLのURLを導入済みドライバ用の postgresql+psycopg2:// へ正規化する。
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
    ("url", "expected"),
    [
        ("postgresql://user:pass@host:5432/db", "postgresql+psycopg2://user:pass@host:5432/db"),
        ("postgres://user:pass@host/db", "postgresql+psycopg2://user:pass@host/db"),
        ("postgresql+psycopg2://user:pass@host/db", "postgresql+psycopg2://user:pass@host/db"),
        # 未導入の psycopg v3 ドライバを指す書式
        (
            "postgresql+psycopg://user:pass@host/db?sslmode=require",
            "postgresql+psycopg2://user:pass@host/db?sslmode=require",
        ),
    ],
)
def test_render_normalizes_postgres_url_to_installed_driver(monkeypatch, url, expected):
    monkeypatch.setattr(app_module, "IS_RENDER", True)
    monkeypatch.setenv("DATABASE_URL", url)
    assert app_module._get_database_uri() == expected


def test_normalized_url_uses_installed_driver():
    from sqlalchemy.engine import make_url

    dialect = make_url("postgresql+psycopg2://user:pass@host/db").get_dialect()
    dialect.import_dbapi()


def test_local_startup_runs_column_migration(monkeypatch):
    """ローカルの既存SQLiteにも、足した列（is_catalog_author など）を入れる。"""
    import manager.db_migration as migration

    calls = []
    flask_app = app_module.create_app(
        config={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "SQLALCHEMY_ENGINE_OPTIONS": {}},
        run_startup=False, register_sockets=False,
    )
    monkeypatch.setattr(app_module, "IS_RENDER", False)
    monkeypatch.setattr(migration, "run_auto_migration", lambda app: calls.append(app))
    monkeypatch.setattr(app_module, "init_app_data", lambda **kwargs: None)
    monkeypatch.setattr(app_module, "read_saved_rooms_with_owners", lambda: None)

    app_module.run_startup_tasks(flask_app)

    assert calls == [flask_app]
