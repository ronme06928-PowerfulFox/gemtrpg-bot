"""Restore a backup into a disposable local PostgreSQL and report what came back.

Never connects to Neon or the local SQLite. The throwaway server listens only on 127.0.0.1 and is
deleted afterwards (unless --keep). Output is counts only, never row contents.
See manuals/operations/postgres_backup_runbook.md.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import backup_postgres as backup  # noqa: E402

WORK_ROOT = ROOT / "_local" / "restore_check"
DB_USER = "restore_check"
DB_NAME = "restored"

APP_CHECK = r"""
import json, os, sys
os.environ["GEMTRPG_DISABLE_DEFAULT_APP"] = "1"
sys.path.insert(0, os.getcwd())
from app import create_app
app = create_app(config={"SQLALCHEMY_DATABASE_URI": os.environ["RESTORE_CHECK_URI"]}, register_sockets=False)
client = app.test_client()
result = {}
for kind in ("skill", "buff", "glossary", "item", "passive", "radiance", "summon"):
    response = client.get(f"/api/get_{kind}_data")
    body = response.get_json(silent=True)
    result[kind] = len(body) if response.status_code == 200 and hasattr(body, "__len__") else f"HTTP {response.status_code}"
from manager.data_manager import read_saved_rooms_with_owners
from manager.room_manager import get_room_state
with app.app_context():
    rooms = read_saved_rooms_with_owners()
    states = [get_room_state(room["name"]) for room in rooms]
result["rooms"] = len(rooms)
result["rooms_loaded"] = sum(1 for state in states if isinstance(state, dict))
print("APP_CHECK " + json.dumps(result))
"""


def _command(args, **kwargs):
    # initdb/pg_ctl spawn children; a file (not a pipe) avoids hanging on Windows.
    with tempfile.TemporaryFile() as log:
        result = subprocess.run(
            [str(value) for value in args], stdout=log, stderr=subprocess.STDOUT, timeout=600,
            env=kwargs.pop("env", backup._clean_environment()),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs,
        )
        log.seek(0)
        output = log.read().decode("utf-8", errors="replace")
    if result.returncode:
        raise backup.BackupError(f"{Path(str(args[0])).name} が失敗しました: {output[-800:]}")
    return output


NEON_OPTION = re.compile(r"^ALTER TABLE ONLY \S+ ALTER COLUMN \S+ SET \(pg_attver=\d+\);$")


def strip_neon_options(source: Path, target: Path):
    """Copy SQL without Neon-only `SET (pg_attver=...)` column options; return how many lines were dropped."""
    dropped = 0
    with source.open(encoding="utf-8", newline="") as reader, target.open("w", encoding="utf-8", newline="") as writer:
        for line in reader:
            if NEON_OPTION.match(line.rstrip("\r\n")):
                dropped += 1
                continue
            writer.write(line)
    return dropped


def latest_backup(root: Path):
    latest = max(backup._completed_backups(root), key=lambda entry: entry[1], default=None)
    if latest is None:
        raise backup.BackupError("戻せる控えがありません。")
    return latest[0]


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _table_counts(psql, port):
    base = [psql, "-h", "127.0.0.1", "-p", port, "-U", DB_USER, "-d", DB_NAME, "-At", "-c"]
    names = _command(base + [
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name",
    ]).split()
    counts = {}
    for name in names:
        counts[name] = int(_command(base + [f'SELECT count(*) FROM public."{name}"']).strip())
    return counts


def restore_check(folder: Path, *, keep=False, check_app=True):
    tools = backup.find_tools()
    manifest = backup.verify_backup(folder, tools)
    bin_dir = tools.pg_restore.parent
    exe = lambda name: bin_dir / (name + (".exe" if os.name == "nt" else ""))
    work = WORK_ROOT / datetime.now(backup.JST).strftime("%Y%m%d_%H%M%S")
    data, port = work / "data", str(_free_port())
    work.mkdir(parents=True)
    started = False
    try:
        _command([exe("initdb"), "-D", data, "-U", DB_USER, "--encoding=UTF8", "--no-locale",
                  "--auth-local=trust", "--auth-host=trust"])
        _command([exe("pg_ctl"), "-D", data, "-l", work / "server.log",
                  "-o", f"-h 127.0.0.1 -p {port} -c ssl=off", "-w", "start"])
        started = True
        _command([exe("createdb"), "-h", "127.0.0.1", "-p", port, "-U", DB_USER, DB_NAME])
        # Neon dumps carry Neon-only column options; plain PostgreSQL rejects them, so drop those lines.
        sql, filtered = work / "restore.sql", work / "restore_filtered.sql"
        _command([exe("pg_restore"), "--no-owner", "--no-acl", "-f", sql, folder / "database.dump"])
        dropped = strip_neon_options(sql, filtered)
        _command([exe("psql"), "-h", "127.0.0.1", "-p", port, "-U", DB_USER, "-d", DB_NAME,
                  "-v", "ON_ERROR_STOP=1", "-q", "-f", filtered])
        report = {
            "backup": folder.name, "backup_created_at": manifest["created_at"],
            "neon_option_lines_dropped": dropped,
            "tables": _table_counts(exe("psql"), port),
        }
        if check_app:
            env = dict(os.environ, RESTORE_CHECK_URI=(
                f"postgresql+psycopg2://{DB_USER}@127.0.0.1:{port}/{DB_NAME}?sslmode=disable"),
                GEMTRPG_DISABLE_DEFAULT_APP="1")
            env.pop("DATABASE_URL", None)
            output = subprocess.run(
                [sys.executable, "-c", APP_CHECK], cwd=ROOT, env=env, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=300,
            )
            line = next((l for l in output.stdout.splitlines() if l.startswith("APP_CHECK ")), None)
            if output.returncode or line is None:
                raise backup.BackupError("戻した DB でアプリを起動できませんでした: " + output.stderr[-800:])
            report["app"] = json.loads(line.removeprefix("APP_CHECK "))
        return report
    finally:
        if started:
            _command([exe("pg_ctl"), "-D", data, "-m", "fast", "-w", "stop"])
        if not keep:
            shutil.rmtree(work)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path, help="戻す控えのフォルダ（省略時は最新）")
    parser.add_argument("--keep", action="store_true", help="使い捨ての DB を消さずに残す（調べる用）")
    parser.add_argument("--no-app", action="store_true", help="アプリでの読み込みを確かめない")
    args = parser.parse_args(argv)
    try:
        folder = args.folder or latest_backup(backup.DEFAULT_BACKUP_ROOT)
        report = restore_check(folder, keep=args.keep, check_app=not args.no_app)
    except (backup.BackupError, OSError, subprocess.SubprocessError) as error:
        print(f"戻す試験に失敗しました: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
