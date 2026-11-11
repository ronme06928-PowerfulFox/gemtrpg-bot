"""スキルの保存形式と既存の配信形式の変換・管理用の検査。"""
from copy import deepcopy
from pathlib import Path
import json
import re

from flask import has_app_context
from manager.cache_paths import SKILLS_CACHE_FILE

_NO_CORRECTION_NOTES = json.loads(
    (Path(__file__).resolve().parents[2] / "data" / "skill_no_correction_notes.json").read_text(encoding="utf-8")
)


def omits_correction(category, notes):
    expected = _NO_CORRECTION_NOTES.get(category) if isinstance(category, str) else None
    if not expected or not isinstance(notes, str):
        return False
    for sentence in re.findall(r"(?:\[\[[^\]\n]+\]\]|[^。\n])+。?", notes):
        plain = re.sub(r"\[\[[^|\]\n]+\|([^\]\n]+)\]\]", r"\1", sentence)
        if plain.strip().removesuffix("。") == expected.removesuffix("。"):
            return True
    return False


PREFIXES = ("Ps", "Pb", "Pp", "Ms", "Mb", "Mp", "D", "B", "C", "E")
TEXT_FIELDS = ("デフォルト名称", "チャットパレット", "分類", "距離", "属性", "取得コスト",
               "基礎威力", "ダイス威力", "コスト", "特記", "発動時効果")
DEFAULTS = {**dict.fromkeys(TEXT_FIELDS, ""), "分類": "補助", "特記処理": {}}


def from_cache(record):
    from .kinds import CatalogValidationError
    payload = {**deepcopy(DEFAULTS), **{key: deepcopy(record[key])
        for key in (*TEXT_FIELDS, "特記処理") if key in record}}
    raw = payload["特記処理"]
    if isinstance(raw, str):
        try:
            payload["特記処理"] = json.loads(raw) if raw.strip() else {}
        except ValueError as exc:
            raise CatalogValidationError({"特記処理": "JSONの形が違います"}) from exc
    if not isinstance(payload["特記処理"], dict):
        raise CatalogValidationError({"特記処理": "オブジェクトが必要です"})
    return payload


def to_memory(payload, entry_id):
    result = {"スキルID": entry_id, **deepcopy(payload)}
    rule = payload.get("特記処理", {})
    result["特記処理"] = json.dumps(rule, ensure_ascii=False) if rule else ""
    tags = []
    category = payload.get("分類", "")
    if category in ("防御", "回避"):
        tags.extend(("守備", category))
    elif category in ("物理", "魔法"):
        tags.append("攻撃")
    elif category == "補助" and "[即時発動]" in payload.get("発動時効果", ""):
        tags.append("即時発動")
    rule_tags = rule.get("tags", [])
    for tag in rule_tags if isinstance(rule_tags, list) else []:
        if tag not in tags:
            tags.append(tag)
    result["tags"] = tags
    return result


SKILL_DEFINITION = {
    "id_prefixes": PREFIXES, "id_pattern": r"(?:Ps|Pb|Pp|Ms|Mb|Mp|D|B|C|E)-\d{2,}",
    "fields": {**dict.fromkeys(TEXT_FIELDS, str), "特記処理": dict},
    "required": ("デフォルト名称",), "defaults": DEFAULTS,
    "choices": {"分類": ("物理", "魔法", "補助", "防御", "回避"),
                "距離": ("", "近接", "遠隔", "広域-個別", "広域-合算"), "属性": ("", "打撃", "斬撃", "貫通")},
    "cache_file": SKILLS_CACHE_FILE, "memory_name": "all_skill_data", "id_field": "スキルID",
    "from_cache": from_cache, "to_memory": to_memory,
}


def _walk(value, path="特記処理"):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def inspect_skill(payload, entry_id, stage, add):
    from manager.json_rule_v2 import (extract_and_normalize_skill_rule_data, JsonRuleV2Error,
                                      EFFECT_TIMINGS, EFFECT_TARGETS)
    from manager.buff_catalog import STATIC_BUFFS, DYNAMIC_PATTERNS
    from manager.skill_catalog_warnings import warn_catalog
    from manager.skill_catalog_validation import _lint_embedded_skill_constraints
    from extensions import all_buff_data
    from models import CatalogEntry, CatalogDraft

    buffs = {key: {"payload": row, "deprecated": row.get("deprecated", False)} for key, row in all_buff_data.items()}
    if has_app_context():
        buffs = {row.entry_id: {"payload": row.payload, "deprecated": row.deprecated}
                 for row in CatalogEntry.query.filter_by(kind="buff").all()}
        buffs.update({row.target_id: {"payload": row.payload, "deprecated": False}
            for row in CatalogDraft.query.filter_by(kind="buff").all() if row.base_revision is None})

    def resolver(buff_id):
        return buffs.get(buff_id, {}).get("payload")

    rule = payload.get("特記処理", {})
    if "tags" in rule and (not isinstance(rule["tags"], list) or any(not isinstance(tag, str) for tag in rule["tags"])):
        add("特記処理.tags", "文字列の配列が必要です")
    for path, row in _walk(rule):
        for key, choices in (("timing", EFFECT_TIMINGS), ("target", EFFECT_TARGETS)):
            if key in row and row[key] not in choices:
                add(f"{path}.{key}", "未定義の選択肢です")
        if "buff_id" in row:
            target = row["buff_id"]
            if not isinstance(target, str) or target not in buffs:
                add(f"{path}.buff_id", f"バフの参照先が存在しません: {target}")
            elif buffs[target]["deprecated"]:
                add(f"{path}.buff_id", f"参照先は廃止されています: {target}", "warning")
        if isinstance(row.get("buff_name"), str):
            name = row["buff_name"]
            if name and not any(item["payload"].get("name") == name for item in buffs.values()) and name not in STATIC_BUFFS and not any(re.fullmatch(item["pattern"], name) for item in DYNAMIC_PATTERNS):
                add(f"{path}.buff_name", f"未登録のバフ名です: {name}", "warning")
    normalized = None
    if rule:
        try:
            # dict入力の暗黙schema補完を避け、保存されるJSONを厳密に読む。
            normalized = extract_and_normalize_skill_rule_data({"rule_data": json.dumps(rule, ensure_ascii=False)},
                skill_id=entry_id, strict=True, buff_resolver=resolver)
        except JsonRuleV2Error as exc:
            add("特記処理" + exc.path.partition(".rule_data")[2], str(exc))
    if normalized:
        for problem in _lint_embedded_skill_constraints(normalized.get("effects"), skill_id=entry_id, source_path="特記処理"):
            add(problem["path"], problem["error"])
    record = to_memory(payload, entry_id or "")
    name, base, dice = (payload.get(key, "") for key in ("デフォルト名称", "基礎威力", "ダイス威力"))
    correction = {"物理": "+1d{物理補正}", "魔法": "+1d{魔法補正}"}.get(payload.get("分類"), "")
    if omits_correction(payload.get("分類"), payload.get("特記")):
        correction = ""
    expected = f"{base}{dice}{correction} 【{entry_id or ''} {name}】"
    if payload.get("チャットパレット", "") != expected:
        add("チャットパレット", f"定型と異なります（例: {expected}）", "warning")
    for warning in warn_catalog({entry_id or "": record}, buff_resolver=resolver):
        add("特記処理", warning["message"], "warning")
