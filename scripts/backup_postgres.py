"""Create private PostgreSQL archives; never restore into a database."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import uuid4
import warnings


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_ROOT = ROOT / "_local" / "backups" / "postgres"
DEFAULT_PG_BIN = ROOT / "_local" / "tools" / "postgresql" / "bin"
REQUIRED_TABLES = {"users", "rooms", "room_members", "owned_characters", "room_log_archives"}
JST = timezone(timedelta(hours=9))


class BackupError(Exception):
    """An operator-readable error containing no connection credentials."""


@dataclass(frozen=True)
class Toolchain:
    pg_dump: Path
    pg_restore: Path
    dump_version: str
    restore_version: str


@dataclass(frozen=True, repr=False)
class Connection:
    host: str
    port: str
    database: str
    user: str
    password: str
    sslmode: str
    channel_binding: str


def parse_connection_url(value: str) -> Connection:
    try:
        url = urlsplit(value.strip())
        if url.scheme not in {"postgres", "postgresql"}:
            raise ValueError()
        host = url.hostname or ""
        port_value = url.port if url.port is not None else 5432
        if not 1 <= port_value <= 65535:
            raise ValueError()
        port = str(port_value)
        user, password = unquote(url.username or ""), unquote(url.password or "")
        database = unquote(url.path.removeprefix("/"))
        options = dict(parse_qsl(url.query, keep_blank_values=True))
        if not host or not user or not password or not re.fullmatch(r"[\w.-]+", database):
            raise ValueError()
        if url.fragment or set(options) - {"sslmode", "channel_binding"}:
            raise ValueError()
        if any(any(char in field for char in "\x00\r\n") for field in (host, user, password, database)):
            raise ValueError()
        if "," in host or "-pooler." in host.lower():
            raise BackupError("NeonのConnection poolingをオフにした直接接続URLを使用してください。")
        sslmode = options.get("sslmode", "require")
        local_test = host.lower() in {"localhost", "127.0.0.1", "::1"} and sslmode == "disable"
        if sslmode not in {"require", "verify-ca", "verify-full"} and not local_test:
            raise BackupError("外部DBへの接続にはsslmode=require以上が必要です。")
        binding = options.get("channel_binding", "prefer")
        if binding not in {"disable", "prefer", "require"}:
            raise ValueError()
        return Connection(host, port, database, user, password, sslmode, binding)
    except (ValueError, TypeError):
        raise BackupError("接続URLの形式を確認してください。URL全体をログやチャットへ貼り付けないでください。") from None


def _clean_environment():
    allowed = {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
        "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
    }
    env = {
        key: value for key, value in os.environ.items()
        if key.upper() in allowed
    }
    env.update(LANG="C", LC_ALL="C")
    return env


@contextmanager
def connection_environment(connection: Connection):
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", prefix="gemdice-pgpass-", delete=False
        ) as handle:
            path = Path(handle.name)
            fields = [connection.host, connection.port, connection.database, connection.user, connection.password]
            handle.write(":".join(field.replace("\\", "\\\\").replace(":", "\\:") for field in fields) + "\n")
        env = _clean_environment()
        env.update(
            PGHOST=connection.host, PGPORT=connection.port, PGDATABASE=connection.database,
            PGUSER=connection.user, PGPASSFILE=str(path), PGSSLMODE=connection.sslmode,
            PGCHANNELBINDING=connection.channel_binding, PGCONNECT_TIMEOUT="15",
            PGAPPNAME="GemDiceBot manual backup", PGOPTIONS="-c default_transaction_read_only=on",
        )
        yield env
    finally:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                raise BackupError(f"一時認証ファイルを削除できませんでした。次のファイルを手動で削除してください: {path}") from None


def _run(args, *, env=None, capture=False):
    try:
        result = subprocess.run(
            [str(arg) for arg in args], env=env if env is not None else _clean_environment(),
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=600,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        raise BackupError("PostgreSQLツールが時間内に完了しませんでした。成功済みのバックアップは維持します。") from None
    except OSError:
        raise BackupError("PostgreSQLツールを起動できません。配置と実行権限を確認してください。") from None
    if result.returncode:
        # Native errors can contain a connection URI or password. Never echo them.
        raise BackupError("PostgreSQLツールが失敗しました。認証・接続先・クライアントの版を確認してください。")
    return result


def find_tools(pg_bin: Path | None = None) -> Toolchain:
    suffix = ".exe" if os.name == "nt" else ""
    paths = []
    versions = []
    for name in ("pg_dump", "pg_restore"):
        candidate = (pg_bin or DEFAULT_PG_BIN) / (name + suffix)
        if not candidate.is_file() and pg_bin is None:
            found = shutil.which(name)
            candidate = Path(found) if found else candidate
        if not candidate.is_file():
            raise BackupError("pg_dumpとpg_restoreが必要です。_local/tools/postgresql/bin/ または --pg-bin を確認してください。")
        output = _run([candidate, "--version"], capture=True).stdout
        match = re.search(r"PostgreSQL\) (\d+(?:\.\d+)*)", output)
        if not match:
            raise BackupError("PostgreSQLツールの版を確認できませんでした。")
        paths.append(candidate)
        versions.append(match[1])
    if versions[0].split(".")[0] != versions[1].split(".")[0]:
        raise BackupError("pg_dumpとpg_restoreのメジャー版をそろえてください。")
    return Toolchain(*paths, *versions)


def _digest(path: Path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def _verify_archive(path: Path, tools: Toolchain):
    listing = _run([tools.pg_restore, "--list", path], capture=True).stdout
    tables = set(re.findall(r"^\d+;\s+\d+\s+\d+\s+TABLE\s+public\s+(\S+)", listing, re.MULTILINE))
    if REQUIRED_TABLES - tables:
        raise BackupError("GemDiceBotの主要テーブルが見つかりません。バックアップ対象DBを確認してください。")
    # No --dbname: generate SQL only and discard stdout, never execute a restore.
    _run([tools.pg_restore, "--no-owner", "--no-acl", "--file=-", path])
    return tables


def _remove_incomplete(folder: Path):
    # Delete only this invocation's files; never recurse into backups.
    for name in ("manifest.json", "database.dump", ".incomplete"):
        (folder / name).unlink(missing_ok=True)
    folder.rmdir()


def create_backup(url: str, tools: Toolchain, output_root: Path) -> Path:
    connection = parse_connection_url(url)
    output_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(JST)
    stage = output_root / (now.strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:12])
    stage.mkdir(mode=0o700)
    published = False
    try:
        (stage / ".incomplete").touch(exist_ok=False)
        dump = stage / "database.dump"
        with connection_environment(connection) as env:
            _run([
                tools.pg_dump, "--format=custom", "--no-owner", "--no-acl",
                "--no-password", "--lock-wait-timeout=10s", "--file", dump,
            ], env=env)
        if not dump.is_file() or not dump.stat().st_size:
            raise BackupError("バックアップファイルが作成されませんでした。")
        tables = _verify_archive(dump, tools)
        manifest = {
            "schema_version": 1, "created_at": now.isoformat(), "format": "postgresql-custom",
            "size_bytes": dump.stat().st_size, "sha256": _digest(dump),
            "pg_dump_version": tools.dump_version, "pg_restore_version": tools.restore_version,
            "checked_tables": sorted(REQUIRED_TABLES), "public_table_count": len(tables),
            "verification": "archive-readable-not-restored",
        }
        with (stage / "manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        (stage / ".incomplete").unlink()
        published = True
        return stage
    finally:
        if not published:
            _remove_incomplete(stage)


def verify_backup(folder: Path, tools: Toolchain):
    if (folder / ".incomplete").exists():
        raise BackupError("未完了のバックアップです。成功済みの原本を使用してください。")
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        dump = folder / "database.dump"
        if (
            manifest["schema_version"] != 1 or manifest["format"] != "postgresql-custom"
            or dump.stat().st_size != manifest["size_bytes"] or _digest(dump) != manifest["sha256"]
        ):
            raise ValueError()
        if int(tools.restore_version.split(".")[0]) < int(manifest["pg_dump_version"].split(".")[0]):
            raise BackupError("作成時より古いpg_restoreでは検査できません。クライアントを更新してください。")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise BackupError("バックアップの記録・サイズ・SHA-256が一致しません。原本を保持して確認してください。") from None
    _verify_archive(dump, tools)
    return manifest


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "引数が不正です。接続URLは引数に含めず、非表示入力を使用してください。\n")


def _read_connection_url():
    value = os.environ.get("GEMDICE_BACKUP_DATABASE_URL")
    if value:
        return value
    if not sys.stdin.isatty():
        raise BackupError("対話端末で実行してください。自動実行では専用環境変数を使用できます。")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass("Neonの直接接続URL（非表示。チャットへ送らない）: ")
        except (getpass.GetPassWarning, EOFError):
            raise BackupError("非表示入力を利用できません。対話端末で実行してください。") from None


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, help="PostgreSQLのbinフォルダ")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="クライアント確認のみ。DBへ接続しない")
    commands.add_parser("backup", help="DBをPCへ保存。元DBへ書き込まない")
    commands.add_parser("verify", help="保管済みファイルを再検査。DBへ接続しない").add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    try:
        tools = find_tools(args.pg_bin)
        if args.command == "doctor":
            print(json.dumps({"ready": True, "pg_dump": tools.dump_version, "pg_restore": tools.restore_version}))
        elif args.command == "backup":
            url = _read_connection_url()
            print("バックアップを取得・検査しています。")
            folder = create_backup(url, tools, DEFAULT_BACKUP_ROOT)
            print(f"バックアップ作成・アーカイブ読込検査に成功しました: {folder}")
        else:
            verify_backup(args.folder, tools)
            print("サイズ・SHA-256・アーカイブ読込検査に成功しました。DBへの復元は行っていません。")
        return 0
    except KeyboardInterrupt:
        print("キャンセルしました。既存バックアップは維持しています。", file=sys.stderr)
        return 130
    except (BackupError, OSError) as error:
        message = str(error) if isinstance(error, BackupError) else "ローカルファイルの操作に失敗しました。保管先を確認してください。"
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
