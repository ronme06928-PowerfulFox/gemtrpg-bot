"""Definition and save-time checks for directly edited Hollow resources."""

from copy import deepcopy
from math import isfinite
import re

from manager.catalog.kinds import get_kind, inspect_buff_effect, inspect_fields, inspect_marks

HOLLOW_IDS = {
    "tier": ("HT", 2), "fixed_floor": ("HF", 2), "relic": ("HR", 2),
    "hollow_event": ("HE", 2), "treasure_chest": ("HC", 2), "drop_table": ("HD", 2),
    "hollow_buff": ("HBu", 2), "hollow_item": ("HI", 2),
}
REWARD_KINDS = {"hollow_buff": "buff", "hollow_item": "item"}
GRADES = ("鉄級", "銅級", "銀級", "金級", "特異級")
EVENT_TYPES = ("normal", "elite", "chest", "miasma", "camp")
ENCOUNTER_TYPES = ("normal", "elite")
TARGET_PREFIXES = {
    "buff": (("buff", "Bu"), ("hollow_buff", "HBu")),
    "item": (("item", "I"), ("hollow_item", "HI")),
    "relic": (("relic", "HR"),),
}


def reward_kind(kind, entry_id):
    if isinstance(entry_id, str):
        for target, prefix in TARGET_PREFIXES[kind]:
            if re.fullmatch(rf"{prefix}-\d{{2,}}", entry_id):
                return target
    return None


def inspect_grade(unit, errors):
    if unit.get("domain") == "hollow" and unit.get("allow_enemy", True):
        tags = [tag for tag in unit.get("tags", []) if isinstance(tag, str) and tag.startswith("等級:")]
        if len(tags) != 1 or tags[0][3:] not in GRADES:
            errors["tags"] = "敵ユニットには等級タグ（等級:鉄級〜等級:特異級）を1つ指定してください"


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _floor(value):
    return _integer(value, 1) and value <= 50


def _multiplier(value):
    return (type(value) is int and value > 0) or (type(value) is float and isfinite(value) and value > 0)


def _object(value, fields, required, path, errors):
    if not isinstance(value, dict):
        errors[path or "payload"] = "オブジェクトが必要です"
        return False
    prefix = path + "." if path else ""
    for key in value.keys() - fields.keys():
        errors[prefix + key] = "未定義の項目です"
    for key in required:
        if key not in value:
            errors[prefix + key] = "必須の項目です"
    for key, check in fields.items():
        if key in value and not check(value[key]):
            errors[prefix + key] = "値の型または範囲が不正です"
    return True


def _array(value, path, errors, *, maximum=None):
    if not isinstance(value, list) or (maximum is not None and len(value) > maximum):
        errors[path] = "配列が必要です" if maximum is None else f"{maximum}件以下の配列が必要です"
        return ()
    return enumerate(value)


def _inspect_tier(data, errors):
    if "floor_min" not in errors and "floor_max" not in errors and data["floor_max"] < data["floor_min"]:
        errors["floor_max"] = "開始階以上の階を指定してください"
    _object(data["event_weights"], dict.fromkeys(EVENT_TYPES, _integer), (), "event_weights", errors)
    encounters = data["encounters"]
    if _object(encounters, dict.fromkeys(ENCOUNTER_TYPES, lambda value: isinstance(value, list)),
               (), "encounters", errors):
        for kind in ENCOUNTER_TYPES:
            path = f"encounters.{kind}"
            for index, row in _array(encounters.get(kind, []), path, errors):
                _object(row, {"formation_id": _text, "weight": _integer},
                        ("formation_id", "weight"), f"{path}[{index}]", errors)


def _inspect_fixed_floor(data, errors):
    if data["type"] == "boss":
        for field in ("formation_id", "stage_id"):
            if not _text(data.get(field)):
                errors[field] = "ボス階で指定してください"
    elif "formation_id" in data:
        errors["formation_id"] = "ボス階の項目です"


def _condition(value):
    return isinstance(value, str) and (value in ("hp_lowest", "bled_last_round")
                                      or (value.startswith("has_tag:") and bool(value[8:].strip())))


def _inspect_relic(data, errors):
    target = data["target"]
    fields = {"type": lambda value: value in ("all", "condition", "nth")}
    mode = target.get("type") if isinstance(target, dict) else None
    if mode == "condition":
        fields["condition"] = _condition
    elif mode == "nth":
        fields["n"] = lambda value: _integer(value, 1)
    _object(target, fields, tuple(fields), "target", errors)


def _inspect_event(data, errors):
    fields = {"label": _text, "difficulty": _integer, "effect": lambda value: isinstance(value, dict),
              "failure_effect": lambda value: isinstance(value, dict),
              "failure_target": lambda value: value in ("selected", "all")}
    effect_fields = {"kind": lambda value: value in ("buff", "item"), "id": _text,
                     "battles": lambda value: _integer(value, 1)}
    for index, row in _array(data["choices"], "choices", errors, maximum=4):
        path = f"choices[{index}]"
        if not _object(row, fields, ("label",), path, errors):
            continue
        for field in ("effect", "failure_effect"):
            if field in row:
                _object(row[field], effect_fields, ("kind", "id"), f"{path}.{field}", errors)
        if "failure_effect" in row:
            for field in ("difficulty", "failure_target"):
                if field not in row:
                    errors[f"{path}.{field}"] = "失敗時の効果と一緒に指定してください"
        elif "failure_target" in row:
            errors[f"{path}.failure_target"] = "失敗時の効果と一緒に指定してください"


def _inspect_drop_table(data, errors):
    fields = {"kind": lambda value: value in ("item", "relic"), "id": _text, "weight": _integer}
    for index, row in _array(data["rows"], "rows", errors):
        _object(row, fields, tuple(fields), f"rows[{index}]", errors)


SCHEMAS = {
    "tier": (
        {"floor_min": _floor, "floor_max": _floor, "description": lambda value: isinstance(value, str),
         "event_weights": lambda value: isinstance(value, dict), "encounters": lambda value: isinstance(value, dict),
         "hp_multiplier": _multiplier, "attack_multiplier": _multiplier},
        {"description": "", "event_weights": {}, "encounters": {}, "hp_multiplier": 1, "attack_multiplier": 1},
        _inspect_tier,
    ),
    "fixed_floor": (
        {"floor": _floor, "type": lambda value: value in ("boss", "town", "camp"),
         "text": lambda value: isinstance(value, str), "formation_id": _text, "stage_id": _text},
        {"text": ""}, _inspect_fixed_floor,
    ),
    "relic": (
        {"rarity": lambda value: value in GRADES, "buff_id": _text,
         **dict.fromkeys(("flavor", "image"), lambda value: isinstance(value, str)),
         "target": lambda value: isinstance(value, dict)},
        {"flavor": "", "image": "", "target": {"type": "all"}}, _inspect_relic,
    ),
    "hollow_event": (
        {"type": lambda value: value in ("miasma", "camp"), "text": lambda value: isinstance(value, str),
         "choices": lambda value: isinstance(value, list)},
        {"text": "", "choices": []}, _inspect_event,
    ),
    "treasure_chest": (
        {"text": lambda value: isinstance(value, str), "drop_table_id": _text},
        {"text": ""}, None,
    ),
    "drop_table": ({"rows": lambda value: isinstance(value, list)}, {}, _inspect_drop_table),
}
OPTIONAL = {"fixed_floor": {"formation_id", "stage_id"}}


def inspect_payload(kind, payload, entry_id, errors, warnings):
    # The unit repository passes a copy, so normalization never mutates the caller.
    if payload.setdefault("domain", "hollow") != "hollow":
        errors["domain"] = "ホロウ専用の資源には hollow を指定してください"
    data = {key: value for key, value in payload.items() if key != "domain"}
    if kind in REWARD_KINDS:
        base = REWARD_KINDS[kind]
        definition = get_kind(base)

        def add(field, message, level="error"):
            (errors if level == "error" else warnings)[field] = message

        invalid = inspect_fields(definition, data, add)
        inspect_marks(data, invalid, add)
        if base == "buff":
            inspect_buff_effect(data, entry_id, "approve", add)
            category = data.get("category")
            if isinstance(category, str) and category and category not in definition["categories"]:
                errors["category"] = "未定義の分類です"
        elif isinstance(data.get("effect"), dict) and data["effect"].get("type") == "buff":
            if not _text(data["effect"].get("buff_id")):
                errors["effect.buff_id"] = "バフIDを指定してください"
        payload.update(deepcopy(definition["defaults"]) | data)
        return

    fields, defaults, inspect = SCHEMAS[kind]
    required = fields.keys() - defaults.keys() - OPTIONAL.get(kind, set())
    _object(data, {"name": _text, **fields}, required, "", errors)
    if not errors:
        payload.update(deepcopy(defaults) | data)
        if inspect:
            inspect(payload, errors)


def links(kind, payload):
    if kind == "tier":
        for encounter, rows in payload.get("encounters", {}).items():
            for index, row in enumerate(rows):
                yield "formation", row["formation_id"], f"encounters.{encounter}[{index}].formation_id"
    elif kind == "fixed_floor":
        for target in ("formation", "stage"):
            field = target + "_id"
            if payload.get(field):
                yield target, payload[field], field
    elif kind == "relic":
        key = payload["buff_id"]
        yield reward_kind("buff", key), key, "buff_id"
    elif kind == "hollow_event":
        for index, choice in enumerate(payload.get("choices", [])):
            for field in ("effect", "failure_effect"):
                if field in choice:
                    effect = choice[field]
                    yield reward_kind(effect["kind"], effect["id"]), effect["id"], f"choices[{index}].{field}.id"
    elif kind == "treasure_chest":
        yield "drop_table", payload["drop_table_id"], "drop_table_id"
    elif kind == "drop_table":
        for index, row in enumerate(payload["rows"]):
            yield reward_kind(row["kind"], row["id"]), row["id"], f"rows[{index}].id"
    elif kind == "hollow_item":
        effect = payload.get("effect", {})
        if effect.get("type") == "buff":
            key = effect["buff_id"]
            yield reward_kind("buff", key), key, "effect.buff_id"
