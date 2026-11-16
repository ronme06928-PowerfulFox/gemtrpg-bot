"""手元のDB（instance/gemtrpg.db）をエージェントから守る仕組みのテスト（AGENTS.md「手元のDBを守る」）。"""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from sqlalchemy import create_engine, text

import app as app_module
from manager import local_db_guard as guard


@pytest.fixture
def local_db(tmp_path, monkeypatch):
    path = tmp_path / "instance" / "gemtrpg.db"
    path.parent.mkdir()
    with sqlite3.connect(path) as con:
        con.execute("create table t (v integer)")
        con.execute("insert into t values (1)")
    monkeypatch.setattr(guard, "LOCAL_DB_PATH", path)
    return path


def _connect(path):
    engine = create_engine("sqlite:///" + Path(path).as_posix())
    try:
        with engine.connect() as con:
            return con.execute(text("select v from t")).scalar()
    finally:
        engine.dispose()


@pytest.mark.parametrize("env", [{"CLAUDECODE": "1"}, {"AI_AGENT": "claude"}, {"CODEX_SANDBOX": "1"}])
def test_agent_markers_are_detected(env):
    assert guard.running_under_agent(env)


def test_plain_shell_is_not_an_agent():
    assert not guard.running_under_agent({"PATH": "x", "HOME": "y"})


def test_agent_cannot_open_the_local_db(local_db, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.delenv(guard.ALLOW_ENV_NAME, raising=False)
    with pytest.raises(Exception, match="手元のDB"):
        _connect(local_db)


def test_agent_can_open_a_copy(local_db, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    copy = tmp_path / "copy.db"
    copy.write_bytes(local_db.read_bytes())
    assert _connect(copy) == 1


def test_user_can_open_the_local_db(local_db, monkeypatch):
    for name in list(os.environ):
        if name in guard.AGENT_ENV_NAMES or name.startswith("CODEX_"):
            monkeypatch.delenv(name)
    assert _connect(local_db) == 1


def test_user_override_opens_the_local_db(local_db, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv(guard.ALLOW_ENV_NAME, "1")
    assert _connect(local_db) == 1


def test_check_path_refuses_scripts_that_write_with_sqlite3(local_db):
    with pytest.raises(guard.LocalDbProtected):
        guard.check_path(local_db, env={"CLAUDECODE": "1"})
    guard.check_path(local_db.with_name("other.db"), env={"CLAUDECODE": "1"})


def test_snapshot_keeps_the_newest_three(local_db, monkeypatch):
    for name in list(os.environ):
        if name in guard.AGENT_ENV_NAMES or name.startswith("CODEX_"):
            monkeypatch.delenv(name)
    start = datetime(2026, 11, 16, 12, 0, 0)
    made = [guard.snapshot_local_db(local_db, now=start + timedelta(seconds=i)) for i in range(5)]
    kept = sorted((local_db.parent / "backups").glob("gemtrpg_*.db"))
    assert kept == made[2:]
    with sqlite3.connect(kept[-1]) as con:
        assert con.execute("select v from t").fetchone() == (1,)


def test_snapshot_ignores_other_databases(local_db, tmp_path):
    assert guard.snapshot_local_db(tmp_path / "copy.db") is None
    assert not (local_db.parent / "backups").exists()


def test_db_option_points_the_app_at_a_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "IS_RENDER", False)
    target = tmp_path / "agent_db" / "gemtrpg.db"
    monkeypatch.setenv("GEMTRPG_DB", str(target))
    assert app_module._get_database_uri() == "sqlite:///" + target.resolve().as_posix()
    assert target.parent.is_dir()


def test_default_uri_is_the_local_db(monkeypatch):
    monkeypatch.setattr(app_module, "IS_RENDER", False)
    monkeypatch.delenv("GEMTRPG_DB", raising=False)
    assert app_module._get_database_uri() == "sqlite:///gemtrpg.db"


def test_cli_accepts_the_db_option():
    assert app_module.build_cli_parser().parse_args(["--db", "x.db"]).db == "x.db"
