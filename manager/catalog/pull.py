"""本番の公開スナップショットをローカルのキャッシュ・公開DBへ反映する。"""
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

import requests

from extensions import db
from manager.cache_paths import GLOSSARY_CACHE_FILE, BUFF_CATALOG_CACHE_FILE, SKILLS_CACHE_FILE
from .kinds import get_kind
from .repository import stage_pulled_catalogs, load_kind_into_memory


DEFAULT_BASE_URL = "https://gemtrpg-diceapp.onrender.com"
SOURCES = {"glossary": "/api/get_glossary_data", "buff": "/api/get_buff_data", "skill": "/api/get_skill_data"}
CACHE_FILES = {"glossary": GLOSSARY_CACHE_FILE, "buff": BUFF_CATALOG_CACHE_FILE, "skill": SKILLS_CACHE_FILE}


class CatalogPullError(ValueError):
    pass


def _validate_snapshot(kind, records):
    if not isinstance(records, dict) or not records:
        raise CatalogPullError(f"{kind}: 空でないID別のオブジェクトが必要です")
    base_definition = get_kind(kind) if kind != "skill" else {
        "id_pattern": r"(?:P[sbp]|M[sbp]|[DBCE])-\d{2,}", "id_field": "スキルID",
        "required": ("デフォルト名称",), "fields": {"デフォルト名称": str, "特記処理": str, "tags": list}}
    definition = base_definition
    for entry_id, row in records.items():
        if not re.fullmatch(definition["id_pattern"], entry_id) or not isinstance(row, dict):
            raise CatalogPullError(f"{kind}: IDまたは行の形が違います: {entry_id}")
        if row.get(definition["id_field"]) != entry_id:
            raise CatalogPullError(f"{kind}: 辞書のキーと行のIDが一致しません: {entry_id}")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in definition["required"]):
            raise CatalogPullError(f"{kind}: 必須の文字列がありません: {entry_id}")
        for field, expected in definition["fields"].items():
            if field in row and not (field == "sort_order" and row[field] is None) and type(row[field]) is not expected:
                raise CatalogPullError(f"{kind}: {entry_id}.{field} の型が違います")
        if "deprecated" in row and type(row["deprecated"]) is not bool:
            raise CatalogPullError(f"{kind}: {entry_id}.deprecated の型が違います")
        for field in ("links", "synonyms", "tags"):
            if field in row and (not isinstance(row[field], list) or any(not isinstance(value, str) for value in row[field])):
                raise CatalogPullError(f"{kind}: {entry_id}.{field} は文字列の配列が必要です")
        if kind == "glossary" and row["category"] not in definition["categories"]:
            raise CatalogPullError(f"glossary: 未定義の分類です: {entry_id}")
        if kind == "buff" and row.get("default_duration", 1) != -1 and row.get("default_duration", 1) < 1:
            raise CatalogPullError(f"buff: 持続が範囲外です: {entry_id}")
        if kind != "skill" and row.keys() - definition["fields"].keys() - {definition["id_field"], "deprecated"}:
            raise CatalogPullError(f"{kind}: 未定義の項目があります: {entry_id}")


def _temporary_file(target, content, suffix):
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=suffix, delete=False) as output:
        path = Path(output.name)
        try:
            output.write(content)
        except Exception:
            output.close()
            path.unlink(missing_ok=True)
            raise
    return path


def pull_catalogs():
    if "RENDER" in os.environ:
        raise CatalogPullError("--pull はRender上では実行できません")
    base_url = os.environ.get("CATALOG_PULL_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment or parts.username is not None:
        raise CatalogPullError("CATALOG_PULL_BASE_URLに公開APIのベースURLを指定してください")
    snapshots = {}
    try:
        for kind, endpoint in SOURCES.items():
            response = requests.get(base_url + endpoint, timeout=60, headers={"Cache-Control": "no-cache"})
            response.raise_for_status()
            records = response.json()
            if kind == "skill" and isinstance(records, dict):
                # システムスキル（SYS-）はコードが正本で、起動時に辞書へ足される。写さない。
                records = {key: value for key, value in records.items() if not key.startswith("SYS-")}
            snapshots[kind] = records
            _validate_snapshot(kind, records)
    except (requests.RequestException, ValueError) as exc:
        raise CatalogPullError(f"公開データの取得・検査に失敗しました: {exc}") from exc

    staged, backups, replaced, retained = {}, {}, [], set()
    try:
        for kind, records in snapshots.items():
            target = CACHE_FILES[kind]
            target.parent.mkdir(parents=True, exist_ok=True)
            backups[kind] = _temporary_file(target, target.read_bytes(), ".backup") if target.exists() else None
            staged[kind] = _temporary_file(target, (json.dumps(records, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"), ".download")
        db.create_all()
        stage_pulled_catalogs(snapshots)
        for kind, path in staged.items():
            os.replace(path, CACHE_FILES[kind])
            replaced.append(kind)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        recovery_errors = []
        for kind in reversed(replaced):
            try:
                if backups[kind] is None:
                    CACHE_FILES[kind].unlink(missing_ok=True)
                else:
                    os.replace(backups[kind], CACHE_FILES[kind])
            except OSError:
                # 復元自体が妨げられた場合、元データの唯一の写しを消さない。
                retained.add(backups[kind])
                recovery_errors.append(str(backups[kind] or CACHE_FILES[kind]))
        if recovery_errors:
            raise CatalogPullError("ファイルを復元できません。元データの退避先または対象: " + ", ".join(recovery_errors)) from exc
        raise CatalogPullError(f"ローカルへの反映に失敗しました: {exc}") from exc
    finally:
        for path in [*staged.values(), *backups.values()]:
            if path is not None and path not in retained:
                path.unlink(missing_ok=True)
    for kind in snapshots:
        load_kind_into_memory(kind)
    return {kind: len(records) for kind, records in snapshots.items()}
