"""Validation and references for unit resources."""
from copy import deepcopy
import re

from models import CatalogEntry
from manager.battle.enemy_behavior import normalize_behavior_profile
from manager.json_rule_v2 import JsonRuleV2Error, normalize_skill_constraints_rows

IDS = {"unit": ("U", 3), "formation": ("F", 3),
       "stage": ("ST", 3), "unit_collection": ("SC", 2)}
SIDES = ("enemy", "ally")
MASTER_FIELDS = {"skills": "skill", "passives": "passive", "radiance": "radiance", "items": "item"}
UNIT_FIELDS = {
    "name": str, "image": str, "scenario": bool, "gm_only": bool,
    "allow_ally": bool, "allow_enemy": bool, "hp": int, "mp": int,
    "initial_hp": int, "initial_mp": int, "params": list,
    "skills": list, "other_lines": list, "passives": list, "radiance": list,
    "items": list, "special_buffs": list, "tags": list, "disabled_tags": list,
    "behavior": dict, "patterns": list, "default_pattern_id": (str, type(None)),
    "collection_id": (str, type(None)),
}


def valid_id(kind, entry_id):
    prefix, width = IDS[kind]
    return isinstance(entry_id, str) and re.fullmatch(rf"{prefix}-\d{{{width},}}", entry_id)


def links(kind, payload):
    if kind != "unit_collection" and payload.get("collection_id"):
        yield "unit_collection", payload["collection_id"], "collection_id"
    if kind == "formation":
        for index, row in enumerate(payload.get("members", [])):
            yield "unit", row["unit_id"], f"members[{index}].unit_id"
    if kind == "stage":
        for side in SIDES:
            field = f"{side}_formation_id"
            if payload.get(field):
                yield "formation", payload[field], field


def master_links(payload):
    for field, kind in MASTER_FIELDS.items():
        for index, value in enumerate(payload.get(field, [])):
            if field in ("skills", "items"):
                value = value.get("id") if isinstance(value, dict) else None
            yield kind, value, f"{field}[{index}]"


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _check_unit(unit, errors, previous):
    for field, expected in UNIT_FIELDS.items():
        if field in unit and not isinstance(unit[field], expected):
            errors[field] = "値の型が不正です"
    if errors:
        return
    for field in ("hp", "mp"):
        maximum = unit.get(field, 0)
        initial = unit.get("initial_" + field, maximum)
        if type(maximum) is not int or type(initial) is not int or not 0 <= initial <= maximum:
            errors[field] = "現在値と最大値が不正です"
    if any(not isinstance(row, dict) or not _text(row.get("label")) for row in unit.get("params", [])):
        errors["params"] = "パラメータにはラベルが必要です"
    if any(not isinstance(line, str) for line in unit.get("other_lines", [])):
        errors["other_lines"] = "パレットの各行には文字列が必要です"
    if any(not isinstance(row, dict) or not isinstance(row.get("name", ""), str)
           or type(row.get("hidden", False)) is not bool for row in unit.get("skills", [])):
        errors["skills"] = "スキルの固有名称または非公開設定が不正です"
    if any(not isinstance(row, dict) or type(row.get("count")) is not int or row["count"] < 0
           for row in unit.get("items", [])):
        errors["items"] = "アイテムの個数には0以上の整数が必要です"
    behavior = unit.get("behavior", {})
    if (any(type(behavior.get(field, False)) is not bool
            for field in ("auto_target", "auto_skill", "show_planned"))
            or behavior.get("slot_mode", "normal") not in ("none", "normal")
            or not isinstance(behavior.get("constraints", []), list)):
        errors["behavior"] = "行動設定が不正です"
    if "behavior" not in errors and behavior.get("constraints"):
        try:
            behavior["constraints"] = normalize_skill_constraints_rows(behavior["constraints"])
        except JsonRuleV2Error as exc:
            errors["behavior.constraints"] = str(exc)
    ids = set()
    skills = {row.get("id") for row in unit.get("skills", [])
              if isinstance(row, dict) and _text(row.get("id"))}
    for index, pattern in enumerate(unit.get("patterns", [])):
        path = f"patterns[{index}]"
        if (not isinstance(pattern, dict) or not _text(pattern.get("id"))
                or pattern["id"] in ids or not _text(pattern.get("name"))
                or not isinstance(pattern.get("profile"), dict)):
            errors[path] = "パターンには一意のID・名前・チャートが必要です"
            continue
        ids.add(pattern["id"])
        profile = normalize_behavior_profile(pattern["profile"])
        pattern["profile"] = profile
        for loop in profile["loops"].values():
            for step in loop["steps"]:
                for skill in step["actions"]:
                    if skill and skill != "__NO_ACTION__" and skill not in skills:
                        errors[path] = f"ユニットが持っていないスキルです: {skill}"
    default = unit.get("default_pattern_id")
    if len(ids) == 1 and not default and not (previous or {}).get("patterns"):
        default = unit["default_pattern_id"] = next(iter(ids))
    if (ids and (not isinstance(default, str) or default not in ids)) or (not ids and default):
        errors["default_pattern_id"] = "パターンがある場合は既定を1つ指定してください"


def inspect_payload(kind, payload, visibility, resources, *, previous=None):
    errors, warnings = {}, {}
    if kind not in IDS:
        return {"kind": "未対応の種類です"}, warnings, payload
    if visibility not in ("public", "staff"):
        errors["visibility"] = "public または staff を指定してください"
    if not isinstance(payload, dict) or not _text(payload.get("name")):
        errors["name"] = "名前が必要です"
        return errors, warnings, payload
    payload = deepcopy(payload)
    if kind == "unit":
        _check_unit(payload, errors, previous)
    if kind in ("formation", "stage"):
        field = "recommended_ally_count" if kind == "formation" else "required_ally_count"
        count = payload.get(field, 0)
        if type(count) is not int or count < 0:
            errors[field] = "人数には0以上の整数が必要です"
    if kind == "stage":
        for field in ("field_effect_profile", "stage_avatar", "background"):
            if field in payload and not isinstance(payload[field], (dict, type(None))):
                errors[field] = "設定にはJSONオブジェクトが必要です"
        tags = payload.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            errors["tags"] = "タグには文字列の配列が必要です"
    if kind == "formation":
        if payload.get("type") not in SIDES:
            errors["type"] = "敵・味方を指定してください"
        elif previous and payload["type"] != previous.get("type"):
            errors["type"] = "作成済みの編成種別は変更できません"
        if not isinstance(payload.get("members"), list):
            errors["members"] = "メンバーの配列が必要です"
        else:
            for index, member in enumerate(payload["members"]):
                if (not isinstance(member, dict) or not _text(member.get("unit_id"))
                        or type(member.get("count")) is not int or member["count"] < 1
                        or not isinstance(member.get("pattern_id"), (str, type(None)))):
                    errors[f"members[{index}]"] = "ユニットID・個数・パターンIDを確認してください"
                else:
                    payload["members"][index] = {key: member.get(key)
                                                for key in ("unit_id", "count", "pattern_id")}
    for field in ("collection_id", "enemy_formation_id", "ally_formation_id"):
        if field in payload and not isinstance(payload[field], (str, type(None))):
            errors[field] = "参照IDが不正です"
    if errors:
        return errors, warnings, payload
    if kind == "unit":
        masters = {(row.kind, row.entry_id): row.deprecated for row in
                   CatalogEntry.query.filter(CatalogEntry.kind.in_(MASTER_FIELDS.values()))}
        for target_kind, key, path in master_links(payload):
            if not _text(key) or masters.get((target_kind, key), True):
                errors[path] = f"存在しないか廃止済みのマスターIDです: {key}"
        payload = {key: value for key, value in payload.items() if key in UNIT_FIELDS}
    for target_kind, key, path in links(kind, payload):
        target = resources.get((target_kind, key))
        if target is None:
            errors[path] = f"参照先がありません: {key}"
            continue
        if target["deprecated"]:
            warnings[path + ".deprecated"] = f"参照先が廃止済みです: {key}"
        if kind in ("formation", "stage") and visibility == "public" and target["visibility"] == "staff":
            warnings[path + ".visibility"] = f"参照先が非公開です: {key}"
        if kind == "stage" and target_kind == "formation" and target["payload"].get("type") != path.split("_")[0]:
            errors[path] = f"編成の陣営が異なります: {key}"
    if kind == "formation":
        for index, member in enumerate(payload["members"]):
            target = resources.get(("unit", member["unit_id"]))
            if target is None:
                continue
            unit = target["payload"]
            side = payload["type"]
            path = f"members[{index}]"
            if not unit.get("allow_" + side, True):
                errors[path + ".unit_id"] = f"{side} として配置できません: {member['unit_id']}"
            pattern = member["pattern_id"]
            unit_patterns = unit.get("patterns")
            pattern_ids = {item.get("id") for item in unit_patterns
                           if isinstance(item, dict) and _text(item.get("id"))} if isinstance(unit_patterns, list) else set()
            if pattern and pattern not in pattern_ids:
                errors[path + ".pattern_id"] = f"パターンが見つかりません: {pattern}"
            if side == "enemy" and not (pattern or unit.get("default_pattern_id")):
                warnings[path + ".pattern_id"] = "行動パターンが未設定です"
    return errors, warnings, payload
