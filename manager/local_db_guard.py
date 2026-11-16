"""手元のDB（instance/gemtrpg.db）をエージェントから守る（AGENTS.md「手元のDBを守る」）。

- エージェントのプロセスから手元のDBへ SQLAlchemy で接続すると、接続の時点で止める。
- 手元のDBで起動するたび、起動時の移行の前に instance/backups/ へ写しを取る。
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine

LOCAL_DB_PATH = Path(__file__).resolve().parents[1] / "instance" / "gemtrpg.db"
AGENT_ENV_NAMES = ("CLAUDECODE", "AI_AGENT")
ALLOW_ENV_NAME = "GEMTRPG_ALLOW_LOCAL_DB"
KEEP_SNAPSHOTS = 3
MESSAGE = (
    "手元のDB（instance/gemtrpg.db）はエージェントから開けません。"
    "写しを作り、python app.py --db _local/agent_db/gemtrpg.db か GEMTRPG_DB=<写し> で指してください（AGENTS.md「手元のDBを守る」）。"
)


class LocalDbProtected(RuntimeError):
    pass


def running_under_agent(env=None):
    env = os.environ if env is None else env
    return any(env.get(name) for name in AGENT_ENV_NAMES) or any(name.startswith("CODEX_") for name in env)


def is_local_db(path):
    if not path:
        return False
    try:
        return Path(path).resolve() == Path(LOCAL_DB_PATH).resolve()
    except (OSError, ValueError):
        return False


def check_path(path, env=None):
    env = os.environ if env is None else env
    if is_local_db(path) and running_under_agent(env) and env.get(ALLOW_ENV_NAME) != "1":
        raise LocalDbProtected(MESSAGE)


@event.listens_for(Engine, "connect")
def _guard_connection(dbapi_connection, _connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        for _seq, _name, path in dbapi_connection.execute("PRAGMA database_list").fetchall():
            check_path(path)


def snapshot_local_db(path, keep=KEEP_SNAPSHOTS, now=None):
    """手元のDBなら instance/backups/ に写しを取り、新しい keep 個だけ残す。写しのパスを返す。"""
    if not is_local_db(path) or not Path(path).exists():
        return None
    check_path(path)
    source = Path(path)
    folder = source.parent / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"gemtrpg_{(now or datetime.now()).strftime('%Y%m%d_%H%M%S_%f')}.db"
    src, dst = sqlite3.connect(source), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in sorted(folder.glob("gemtrpg_*.db"))[:-keep]:
        old.unlink()
    return target
