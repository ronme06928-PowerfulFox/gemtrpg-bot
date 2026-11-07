"""種類ごとの項目、ID、検査、配信用辞書の定義。"""
from copy import deepcopy
import re


class CatalogValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


KINDS = {
    "glossary": {
        "id_prefix": "W-",
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
}
DRAFT_ID_PATTERN = r"X-[0-9a-fA-F]{8}"


def get_kind(kind):
    if kind not in KINDS:
        raise CatalogValidationError({"kind": "未対応の種類です"})
    return KINDS[kind]


def validate_entry_id(kind, entry_id):
    if not isinstance(entry_id, str) or not re.fullmatch(get_kind(kind)["id_pattern"], entry_id):
        raise CatalogValidationError({"entry_id": "正式IDの形が違います"})


def validate_payload(kind, payload, *, entry_id=None, published_ids=(), draft_ids=()):
    definition = get_kind(kind)
    if not isinstance(payload, dict):
        raise CatalogValidationError({"payload": "オブジェクトが必要です"})
    errors = {}
    for field in payload.keys() - definition["fields"].keys():
        errors[field] = "未定義の項目です"
    for field in definition["required"]:
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors[field] = "必須の文字列です"
    for field, value in payload.items():
        expected = definition["fields"].get(field)
        if expected is None or (field == "sort_order" and value is None):
            continue
        if type(value) is not expected:
            errors[field] = "型が違います"
    if isinstance(payload.get("category"), str) and payload["category"] not in definition["categories"]:
        errors["category"] = "未定義の分類です"
    for field in ("links", "synonyms"):
        if isinstance(payload.get(field), list) and any(not isinstance(v, str) for v in payload[field]):
            errors[field] = "文字列の配列が必要です"
    if "links" not in errors:
        for target in payload.get("links", []):
            if target == entry_id:
                errors["links"] = "自分自身へのリンクは指定できません"
            elif target not in published_ids and not (re.fullmatch(DRAFT_ID_PATTERN, target) and target in draft_ids):
                errors["links"] = f"リンク先が存在しません: {target}"
    if errors:
        raise CatalogValidationError(errors)
    return {**deepcopy(definition["defaults"]), **deepcopy(payload)}


def to_memory_entry(kind, entry):
    return {get_kind(kind)["id_field"]: entry.entry_id,
            **deepcopy(entry.payload), "deprecated": entry.deprecated}



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


def validate_public_payload(payload):
    errors = {field: "未公開の仮IDが残っています" for field, value in payload.items()
              if _has_draft_id(value)}
    if errors:
        raise CatalogValidationError(errors)


def replace_draft_id(payload, target, entry_id):
    """参照用の配列と文章中の参照を、未完成の下書きも含めて置き換える。"""
    if isinstance(payload, str):
        return _draft_id_regex(target).sub(lambda _: entry_id, payload)
    if isinstance(payload, list):
        return [replace_draft_id(value, target, entry_id) for value in payload]
    if isinstance(payload, dict):
        return {key: replace_draft_id(value, target, entry_id) for key, value in payload.items()}
    return payload
