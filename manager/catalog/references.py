"""参照箇所は公開済みの辞書から求める。ファイルや別キャッシュへ戻らない。"""
import re
import json
import extensions
from models import CatalogEntry
from .kinds import KINDS, get_kind

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



def _id_paths(value, entry_id, path=""):
    if isinstance(value, str):
        if value == entry_id:
            yield path
            return
        try:
            parsed = json.loads(value)
        except ValueError:
            return
        if isinstance(parsed, (dict, list)):
            yield from _id_paths(parsed, entry_id, path)
    elif isinstance(value, dict):
        for key, child in value.items():
            if key == entry_id:
                yield f"{path}.{key}" if path else key
            yield from _id_paths(child, entry_id, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _id_paths(child, entry_id, f"{path}[{index}]")



def _target_paths(payload, kind, entry_id, buff_name=None):
    if kind == "glossary":
        return _text_paths(payload, entry_id)
    if kind == "buff":
        return _buff_paths(payload, entry_id, buff_name)
    return _id_paths(payload, entry_id)


def _display_name(payload, entry_id):
    return payload.get("display_name") or payload.get("デフォルト名称") or payload.get("name") or entry_id


def find_outgoing(kind, entry_id):
    get_kind(kind)
    source = CatalogEntry.query.filter_by(kind=kind, entry_id=entry_id).first()
    if source is None:
        return []
    links = source.payload.get("links", []) if kind == "glossary" else []
    outgoing = []
    targets = CatalogEntry.query.filter(CatalogEntry.kind.in_(KINDS)).order_by(CatalogEntry.kind, CatalogEntry.entry_id)
    for target in targets:
        if (target.kind, target.entry_id) == (kind, entry_id):
            continue
        paths = list(_target_paths(source.payload, target.kind, target.entry_id, target.payload.get("name")))
        if target.kind == "glossary" and target.entry_id in links:
            paths.append("links")
        for path in dict.fromkeys(paths):
            outgoing.append({"kind": target.kind, "entry_id": target.entry_id,
                             "display_name": _display_name(target.payload, target.entry_id), "path": path})
    return outgoing


def find_references(kind, entry_id, *, include_staff=False):
    get_kind(kind)
    references = []
    buff_name = None
    if kind == "buff":
        entry = CatalogEntry.query.filter_by(kind=kind, entry_id=entry_id).first()
        if entry is None:
            return []
        buff_name = entry.payload["name"]
    if kind == "glossary":
        for row in CatalogEntry.query.filter_by(kind=kind).order_by(CatalogEntry.entry_id).all():
            if row.entry_id != entry_id and entry_id in row.payload.get("links", []):
                references.append({"kind": kind, "entry_id": row.entry_id,
                                   "display_name": row.payload["display_name"], "path": "links"})
    for source_kind, definition in KINDS.items():
        records = getattr(extensions, definition["memory_name"])
        for source_id, payload in sorted(records.items()):
            if source_kind == kind and source_id == entry_id:
                continue
            for path in _target_paths(payload, kind, entry_id, buff_name):
                references.append({"kind": source_kind, "entry_id": source_id,
                                   "display_name": _display_name(payload, source_id), "path": path})
    if kind in ("skill", "passive", "radiance", "item"):
        from manager.units.repository import entries
        from manager.units.validation import master_links

        for (_, source_id), row in entries(include_staff=include_staff).items():
            if row["kind"] != "unit":
                continue
            for target_kind, target, path in master_links(row["payload"]):
                if (target_kind, target) == (kind, entry_id):
                    references.append({"kind": "unit", "entry_id": source_id,
                                       "display_name": row["payload"]["name"], "path": path})
    return references
