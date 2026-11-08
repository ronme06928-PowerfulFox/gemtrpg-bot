"""公開データの参照箇所を保存せず、その時点の中身から求める。"""
import re
import json

from extensions import all_skill_data, all_buff_data
from models import CatalogEntry
from .kinds import get_kind


GLOSSARY_MARKUP = re.compile(r"\[\[(W-\d{2,})(?:\|[^\]]*)?\]\]")


def _text_paths(value, target_id, path=""):
    if isinstance(value, str):
        if any(match.group(1) == target_id for match in GLOSSARY_MARKUP.finditer(value)):
            yield path
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _text_paths(child, target_id, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _text_paths(child, target_id, f"{path}[{index}]")


def find_references(kind, entry_id):
    get_kind(kind)
    if kind == "skill":
        return _skill_references(entry_id)
    if kind == "buff":
        return _buff_references(entry_id)
    references = []
    for row in CatalogEntry.query.filter_by(kind=kind).order_by(CatalogEntry.entry_id).all():
        if entry_id in row.payload.get("links", []):
            references.append({"kind": kind, "entry_id": row.entry_id,
                               "display_name": row.payload["display_name"], "path": "links"})
    for source_kind, records in (("skill", all_skill_data), ("buff", all_buff_data)):
        for source_id, payload in sorted(records.items()):
            name = payload.get("display_name") or payload.get("デフォルト名称") or payload.get("name") or source_id
            for path in _text_paths(payload, entry_id):
                references.append({"kind": source_kind, "entry_id": source_id,
                                   "display_name": name, "path": path})
    return references


def _buff_paths(value, entry_id, name, path=""):
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return
        if isinstance(parsed, (dict, list)):
            yield from _buff_paths(parsed, entry_id, name, path)
    elif isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if (key == "buff_id" and child == entry_id) or (key == "buff_name" and child == name):
                yield child_path
            else:
                yield from _buff_paths(child, entry_id, name, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _buff_paths(child, entry_id, name, f"{path}[{index}]")


def _buff_references(entry_id):
    from manager.items.loader import item_loader
    from manager.passives.loader import passive_loader
    from manager.radiance.loader import radiance_loader
    from manager.cache_paths import (ITEMS_CACHE_FILE, PASSIVES_CACHE_FILE,
                                     RADIANCE_CACHE_FILE, SKILLS_CACHE_FILE, load_json_cache)
    entry = CatalogEntry.query.filter_by(kind="buff", entry_id=entry_id).first()
    if entry is None:
        return []
    sources = [("skill", all_skill_data or load_json_cache(SKILLS_CACHE_FILE) or {})]
    for kind, loader, cache_file in (("item", item_loader, ITEMS_CACHE_FILE),
            ("passive", passive_loader, PASSIVES_CACHE_FILE),
            ("radiance", radiance_loader, RADIANCE_CACHE_FILE)):
        # 参照の検索がSheetsの再取得やキャッシュの書き込みを起こさないようにする。
        records = loader._cache if loader._cache is not None else load_json_cache(cache_file)
        sources.append((kind, records or {}))
    references = []
    for kind, records in sources:
        for source_id, payload in sorted(records.items()):
            name = payload.get("display_name") or payload.get("デフォルト名称") or payload.get("name") or source_id
            for path in _buff_paths(payload, entry_id, entry.payload["name"]):
                references.append({"kind": kind, "entry_id": source_id,
                                   "display_name": name, "path": path})
    return references


def _skill_paths(value, entry_id, path=""):
    if isinstance(value, str):
        if value == entry_id:
            yield path
            return
        try:
            parsed = json.loads(value)
        except ValueError:
            return
        if isinstance(parsed, (dict, list)):
            yield from _skill_paths(parsed, entry_id, path)
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _skill_paths(child, entry_id, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _skill_paths(child, entry_id, f"{path}[{index}]")


def _skill_references(entry_id):
    from manager.items.loader import item_loader
    from manager.passives.loader import passive_loader
    from manager.radiance.loader import radiance_loader
    from manager.cache_paths import (ITEMS_CACHE_FILE, PASSIVES_CACHE_FILE,
        RADIANCE_CACHE_FILE, SKILLS_CACHE_FILE, SUMMON_TEMPLATES_CACHE_FILE, load_json_cache)
    sources = [("skill", all_skill_data or load_json_cache(SKILLS_CACHE_FILE) or {})]
    for kind, loader, cache in (("item", item_loader, ITEMS_CACHE_FILE),
            ("passive", passive_loader, PASSIVES_CACHE_FILE),
            ("radiance", radiance_loader, RADIANCE_CACHE_FILE)):
        sources.append((kind, loader._cache if loader._cache is not None else load_json_cache(cache) or {}))
    sources.append(("summon", load_json_cache(SUMMON_TEMPLATES_CACHE_FILE) or {}))
    references = []
    for kind, records in sources:
        for source_id, payload in sorted(records.items()):
            if kind == "skill" and source_id == entry_id:
                continue
            name = payload.get("デフォルト名称") or payload.get("name") or source_id
            for path in _skill_paths(payload, entry_id):
                references.append({"kind": kind, "entry_id": source_id,
                                   "display_name": name, "path": path})
    return references
