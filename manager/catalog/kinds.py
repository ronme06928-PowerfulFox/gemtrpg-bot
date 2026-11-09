"""種類ごとの項目、ID、検査、配信用辞書の定義。"""
from copy import deepcopy
import re

from manager.cache_paths import GLOSSARY_CACHE_FILE, BUFF_CATALOG_CACHE_FILE
from .skills import SKILL_DEFINITION
from .resources import RESOURCE_DEFINITIONS, inspect_resource


class CatalogValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


KINDS = {
    **RESOURCE_DEFINITIONS,
    "skill": SKILL_DEFINITION,
    "glossary": {
        "id_prefix": "W-",
        "cache_file": GLOSSARY_CACHE_FILE,
        "id_pattern": r"W-\d{2,}",
        "fields": {
            "display_name": str, "category": str, "short": str, "long": str,
            "flavor": str, "links": list, "synonyms": list, "sort_order": int,
        },
        "required": ("display_name", "category"),
        "defaults": {"short": "", "long": "", "flavor": "", "links": [],
                     "synonyms": [], "sort_order": None},
        "categories": ("ルール", "タイミング", "効果", "バフ", "状態異常", "スキルタグ", "デバフ"),
        "memory_name": "all_glossary_data",
        "id_field": "term_id",
    },
    "buff": {
        "id_prefix": "Bu-", "id_pattern": r"Bu-\d{2,}",
        "cache_file": BUFF_CATALOG_CACHE_FILE,
        "fields": {"name": str, "display_name": str, "description": str,
                   "flavor": str, "effect": dict, "default_duration": int},
        "required": ("name",),
        "defaults": {"display_name": "", "description": "", "flavor": "",
                     "effect": {}, "default_duration": 1},
        "memory_name": "all_buff_data", "id_field": "id",
    },
}
DRAFT_ID_PATTERN = r"X-[0-9a-fA-F]{8}"


def get_kind(kind):
    if kind not in KINDS:
        raise CatalogValidationError({"kind": "未対応の種類です"})
    return KINDS[kind]


def validate_entry_id(kind, entry_id):
    if not isinstance(entry_id, str) or not re.fullmatch(get_kind(kind)["id_pattern"], entry_id):
        raise CatalogValidationError({"entry_id": "正式IDの形が違います"})


def _reference_context():
    from flask import has_app_context
    if not has_app_context():
        return {}, set(), []
    from models import CatalogEntry, CatalogDraft
    glossary = {row.entry_id: row for row in CatalogEntry.query.filter_by(kind="glossary").all()}
    drafts = {row.target_id for row in CatalogDraft.query.filter_by(kind="glossary").all()
              if row.base_revision is None}
    buffs = CatalogEntry.query.filter_by(kind="buff").all()
    return glossary, drafts, buffs


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def inspect_payload(kind, payload, *, entry_id=None, stage, published_ids=None, draft_ids=None):
    """保存を妨げずに問題を返す。参照はDBの現在の公開版・用語下書きで判定する。"""
    definition = get_kind(kind)
    if stage not in ("draft", "submit", "approve"):
        raise ValueError("Unknown inspection stage")
    problems = []

    def add(field, message, level="error"):
        problem = {"level": level, "field": field, "message": message}
        if problem not in problems:
            problems.append(problem)

    if not isinstance(payload, dict):
        add("payload", "オブジェクトが必要です")
        return problems
    for field in sorted(payload.keys() - definition["fields"].keys()):
        add(field, "未定義の項目です")
    for field in definition["required"]:
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            add(field, "必須の文字列です")
    invalid = set()
    for field, value in payload.items():
        expected = definition["fields"].get(field)
        if expected is None or (field == "sort_order" and value is None):
            continue
        if type(value) is not expected:
            add(field, "型が違います")
            invalid.add(field)
    if kind == "glossary":
        if isinstance(payload.get("category"), str) and payload["category"] not in definition["categories"]:
            add("category", "未定義の分類です")
        for field in ("links", "synonyms"):
            if isinstance(payload.get(field), list) and any(not isinstance(v, str) for v in payload[field]):
                add(field, "文字列の配列が必要です")
                invalid.add(field)
    for field, choices in definition.get("choices", {}).items():
        if field in payload and field not in invalid and payload[field] not in choices:
            add(field, "未定義の選択肢です")
    if kind == "skill" and not invalid:
        from .skills import inspect_skill
        inspect_skill(payload, entry_id, stage, add)
    if kind in RESOURCE_DEFINITIONS:
        inspect_resource(kind, payload, invalid, add)
    glossary, drafts, buffs = _reference_context()
    published = set(glossary) if published_ids is None or kind != "glossary" else set(published_ids)
    drafts = drafts if draft_ids is None or kind != "glossary" else set(draft_ids)
    if kind == "buff":
        duration = payload.get("default_duration", 1)
        if type(duration) is int and duration != -1 and duration < 1:
            add("default_duration", "-1 または1以上の整数が必要です")
        effect = payload.get("effect", {})
        if isinstance(effect, dict) and effect.get("type") == "plugin":
            # 戦闘はプラグインをバフIDで呼ぶ（BUFF_IDS）。effect.name は判定に使わない。
            from plugins.buffs.registry import buff_registry
            if not buff_registry.list_registered():
                buff_registry.auto_discover()
            if buff_registry.get_handler(entry_id) is None:
                if stage != "approve" and isinstance(entry_id, str) and re.fullmatch(DRAFT_ID_PATTERN, entry_id):
                    add("effect.type", "正式なIDをプラグインに登録するまで効果は動きません", "warning")
                else:
                    add("effect.type", "このIDのプラグインがコードにありません")
        for row in buffs:
            if row.entry_id == entry_id:
                if row.payload.get("name") != payload.get("name"):
                    add("name", "公開済みの内部名は変更できません")
            elif row.payload.get("name") == payload.get("name"):
                add("name", "内部名がほかのバフと重複しています")

    def reference(field, target):
        if kind == "glossary" and target == entry_id:
            add(field, "自分自身へのリンクは指定できません")
        elif target not in published and target not in drafts:
            add(field, f"リンク先が存在しません: {target}")
        elif target in glossary and glossary[target].deprecated:
            add(field, f"参照先は廃止されています: {target}", "warning")

    if kind == "glossary" and "links" not in invalid:
        for target in payload.get("links", []):
            reference("links", target)
    markup = re.compile(r"\[\[((?:W-\d{2,}|X-[0-9a-fA-F]{8}))(?:\|[^\]]*)?\]\]")
    for field, value in payload.items():
        for text in _strings(value):
            for match in markup.finditer(text):
                # 自分の本文中の参照はlinksの自己参照禁止とは別。
                target = match.group(1)
                if kind == "glossary" and target == entry_id:
                    continue
                reference(field, target)
        if stage == "approve" and _has_draft_id(value):
            add(field, "未公開の仮IDが残っています")
    return problems


def validate_payload(kind, payload, *, entry_id=None, published_ids=None, draft_ids=None, stage="submit"):
    problems = inspect_payload(kind, payload, entry_id=entry_id, stage=stage,
                               published_ids=published_ids, draft_ids=draft_ids)
    errors = {p["field"]: p["message"] for p in problems if p["level"] == "error"}
    if errors:
        raise CatalogValidationError(errors)
    return {**deepcopy(get_kind(kind)["defaults"]), **deepcopy(payload)}


def to_memory_entry(kind, entry):
    definition = get_kind(kind)
    result = (definition["to_memory"](entry.payload, entry.entry_id) if "to_memory" in definition
              else {definition["id_field"]: entry.entry_id, **deepcopy(entry.payload)})
    # バフの既存配信形式を保ち、廃止したときだけ印を足す。
    if kind == "glossary" or entry.deprecated:
        result["deprecated"] = entry.deprecated
    return result



def _draft_id_regex(target=None):
    return re.compile(r"(?<![A-Za-z0-9_-])" + (re.escape(target) if target else DRAFT_ID_PATTERN)
                      + r"(?![A-Za-z0-9_-])")


def _has_draft_id(value):
    if isinstance(value, str):
        return bool(_draft_id_regex().search(value))
    if isinstance(value, list):
        return any(_has_draft_id(item) for item in value)
    if isinstance(value, dict):
        return any(_has_draft_id(item) for item in value.values())
    return False


def validate_public_payload(kind, payload, *, entry_id=None):
    return validate_payload(kind, payload, entry_id=entry_id, stage="approve")


def replace_draft_id(payload, target, entry_id):
    """参照用の配列と文章中の参照を、未完成の下書きも含めて置き換える。"""
    if isinstance(payload, str):
        return _draft_id_regex(target).sub(lambda _: entry_id, payload)
    if isinstance(payload, list):
        return [replace_draft_id(value, target, entry_id) for value in payload]
    if isinstance(payload, dict):
        return {key: replace_draft_id(value, target, entry_id) for key, value in payload.items()}
    return payload
