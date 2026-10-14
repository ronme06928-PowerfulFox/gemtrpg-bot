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


def test_requirements_pin_sqlalchemy_to_tested_version():
    # 2026-10-15: SQLAlchemy 未固定のため Render の新規ビルドに 2.1.4 が入り、
    # postgresql:// の既定ドライバが未導入の psycopg v3 になって起動失敗した。
    from pathlib import Path

    import sqlalchemy

    root = Path(__file__).resolve().parents[1]
    lines = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pins = [line for line in lines if line.lower().startswith("sqlalchemy==")]
    assert pins == [f"SQLAlchemy=={sqlalchemy.__version__}"]
