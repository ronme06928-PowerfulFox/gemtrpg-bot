"""公開データの参照箇所を保存せず、その時点の中身から求める。"""
import re

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
