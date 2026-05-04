import copy
import json
import re

from manager.json_rule_audit import append_audit

SCHEMA_SKILL_RULE_V2 = "skill_json_rule_v2"
LEGACY_SCHEMA_ALIASES = {"gdb.rule.v2"}
PHASE3_STRICT_DEFAULT = True
PHASE3_REQUIRE_SCHEMA = True
PHASE3_REQUIRE_BUFF_ID_FOR_APPLY = True
PHASE3_REQUIRE_BUFF_ID_FOR_REMOVE = True

SKILL_RULE_SOURCE_KEYS = [
    "rule_data",
    "rule_data_json",
    "rule_json",
    "rule",
    "ruleData",
    "special_rule",
    "特記処理",
]

STATE_STACK_SUM_PARAM_KEYS = {
    "状態異常スタック合計",
    "状態異常合算",
    "status_stack_sum",
    "status_stack_total",
    "debuff_stack_sum",
}

_STATE_STACK_SUM_PARAM_KEYSET_LOWER = {k.lower() for k in STATE_STACK_SUM_PARAM_KEYS}


class JsonRuleV2Error(ValueError):
    def __init__(self, message, *, path=""):
        self.path = str(path or "")
        super().__init__(f"{self.path}: {message}" if self.path else str(message))


def _coerce_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _safe_json_object_loads(raw, *, path=""):
    try:
        parsed = json.loads(str(raw))
    except Exception as exc:
        raise JsonRuleV2Error(f"invalid JSON object ({exc})", path=path) from exc
    if not isinstance(parsed, dict):
        raise JsonRuleV2Error("JSON root must be object", path=path)
    return parsed


def _resolve_buff_name_by_id(buff_id):
    from manager.buff_catalog import get_buff_by_id

    data = get_buff_by_id(str(buff_id or "").strip())
    if not isinstance(data, dict):
        return ""
    return str(data.get("name", "") or "").strip()


def parse_status_stack_sum_param(param_value):
    raw = str(param_value or "").strip()
    if not raw:
        return None

    m = re.match(r"^(.+?)\s*[:：]\s*(.*)$", raw)
    if not m:
        if raw.lower() in _STATE_STACK_SUM_PARAM_KEYSET_LOWER:
            return {"is_stack_sum": True, "names": [], "error": "state names are required"}
        return None

    key = str(m.group(1) or "").strip().lower()
    if key not in _STATE_STACK_SUM_PARAM_KEYSET_LOWER:
        return None

    names_raw = str(m.group(2) or "").strip()
    if not names_raw:
        return {"is_stack_sum": True, "names": [], "error": "state names are required"}

    names = []
    for token in re.split(r"[,\s、，/|・]+", names_raw):
        name = str(token or "").strip()
        if not name:
            continue
        if name not in names:
            names.append(name)
    if not names:
        return {"is_stack_sum": True, "names": [], "error": "state names are required"}

    return {"is_stack_sum": True, "names": names, "error": ""}


def _validate_condition_param_notation(param_value, *, path):
    parsed = parse_status_stack_sum_param(param_value)
    if parsed is None:
        return
    if parsed.get("error"):
        raise JsonRuleV2Error(
            "status stack sum param must enumerate state names (e.g. 状態異常スタック合計:出血,破裂,亀裂,戦慄,荊棘)",
            path=path,
        )


def _validate_condition_row(condition_obj, *, path):
    if condition_obj is None:
        return
    if not isinstance(condition_obj, dict):
        raise JsonRuleV2Error("condition must be object", path=path)
    _validate_condition_param_notation(condition_obj.get("param"), path=f"{path}.param")


def _normalize_cost_entries(rows, *, path=""):
    if rows is None:
        return []
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise JsonRuleV2Error("cost must be list", path=path)
    out = []
    for idx, row in enumerate(rows):
        row_path = f"{path}[{idx}]"
        if not isinstance(row, dict):
            raise JsonRuleV2Error("cost entry must be object", path=row_path)
        c_type = str(row.get("type", "") or "").strip()
        c_value = _coerce_int(row.get("value", 0), 0)
        if not c_type or c_value <= 0:
            continue
        out.append({"type": c_type, "value": c_value})
    return out


def _normalize_effect_rows(
    effects,
    *,
    path="effects",
    require_buff_id_for_apply=False,
    require_buff_id_for_remove=False,
):
    if effects is None:
        return []
    if isinstance(effects, dict):
        effects = [effects]
    if not isinstance(effects, list):
        raise JsonRuleV2Error("effects must be list", path=path)

    out = []
    for idx, effect in enumerate(effects):
        e_path = f"{path}[{idx}]"
        if not isinstance(effect, dict):
            raise JsonRuleV2Error("effect entry must be object", path=e_path)
        row = copy.deepcopy(effect)
        effect_type = str(row.get("type", "") or "").strip().upper()
        if not effect_type:
            raise JsonRuleV2Error("effect.type is required", path=f"{e_path}.type")
        row["type"] = effect_type
        _validate_condition_row(row.get("condition"), path=f"{e_path}.condition")

        if effect_type in {"APPLY_BUFF", "REMOVE_BUFF"}:
            buff_id = str(row.get("buff_id", "") or "").strip()
            buff_name = str(row.get("buff_name", "") or "").strip()
            if not buff_id and not buff_name:
                raise JsonRuleV2Error(
                    "APPLY/REMOVE_BUFF needs buff_id or buff_name",
                    path=e_path,
                )
            if effect_type == "APPLY_BUFF" and require_buff_id_for_apply and not buff_id:
                raise JsonRuleV2Error(
                    "APPLY_BUFF requires buff_id in skill_json_rule_v2",
                    path=e_path,
                )
            if effect_type == "REMOVE_BUFF" and require_buff_id_for_remove and not buff_id:
                raise JsonRuleV2Error(
                    "REMOVE_BUFF requires buff_id in skill_json_rule_v2",
                    path=e_path,
                )
            resolved = _resolve_buff_name_by_id(buff_id) if buff_id else ""
            if buff_id and not resolved:
                raise JsonRuleV2Error(
                    f"cannot resolve buff_name from buff_id '{buff_id}'",
                    path=e_path,
                )
            if buff_id and buff_name and resolved and str(buff_name) != str(resolved):
                raise JsonRuleV2Error(
                    f"buff_name '{buff_name}' does not match buff_id '{buff_id}' ({resolved})",
                    path=e_path,
                )
            if buff_id and not buff_name:
                buff_name = resolved
            if buff_id:
                row["buff_id"] = buff_id
            row["buff_name"] = buff_name

        out.append(row)
    return out


def normalize_skill_rule_object(rule_obj, *, source_path="rule_data", strict=PHASE3_STRICT_DEFAULT):
    if rule_obj is None:
        rule_obj = {}
    if not isinstance(rule_obj, dict):
        raise JsonRuleV2Error("rule object must be dict", path=source_path)

    out = copy.deepcopy(rule_obj)
    raw_schema = str(out.get("schema", "") or "").strip()
    explicit_v2 = raw_schema == SCHEMA_SKILL_RULE_V2
    schema = raw_schema
    if not schema:
        if strict and PHASE3_REQUIRE_SCHEMA:
            raise JsonRuleV2Error(
                "schema is required in strict mode",
                path=f"{source_path}.schema",
            )
        out["schema"] = SCHEMA_SKILL_RULE_V2
    elif schema in LEGACY_SCHEMA_ALIASES:
        if strict:
            raise JsonRuleV2Error(
                f"legacy schema alias '{schema}' is not accepted in strict mode",
                path=f"{source_path}.schema",
            )
        out["schema"] = SCHEMA_SKILL_RULE_V2
    elif schema != SCHEMA_SKILL_RULE_V2 and strict:
        raise JsonRuleV2Error(
            f"unsupported schema '{schema}' in strict mode",
            path=f"{source_path}.schema",
        )

    # normalize common containers
    out["effects"] = _normalize_effect_rows(
        out.get("effects", []),
        path=f"{source_path}.effects",
        require_buff_id_for_apply=(explicit_v2 and PHASE3_REQUIRE_BUFF_ID_FOR_APPLY),
        require_buff_id_for_remove=(explicit_v2 and PHASE3_REQUIRE_BUFF_ID_FOR_REMOVE),
    )
    power_bonus_rows = out.get("power_bonus", [])
    if isinstance(power_bonus_rows, dict):
        power_bonus_rows = [power_bonus_rows]
    if power_bonus_rows is None:
        power_bonus_rows = []
    if not isinstance(power_bonus_rows, list):
        raise JsonRuleV2Error("power_bonus must be list", path=f"{source_path}.power_bonus")
    for idx, row in enumerate(power_bonus_rows):
        pb_path = f"{source_path}.power_bonus[{idx}]"
        if not isinstance(row, dict):
            raise JsonRuleV2Error("power_bonus entry must be object", path=pb_path)
        _validate_condition_row(row.get("condition"), path=f"{pb_path}.condition")
        _validate_condition_param_notation(row.get("param"), path=f"{pb_path}.param")
    out["power_bonus"] = power_bonus_rows
    out["cost"] = _normalize_cost_entries(out.get("cost", []), path=f"{source_path}.cost")
    if "tags" in out and not isinstance(out.get("tags"), list):
        tags = out.get("tags")
        out["tags"] = [str(tags)] if tags not in [None, ""] else []
    append_audit(
        "normalize_skill_rule_object_ok",
        source_path=source_path,
        strict=bool(strict),
        schema=out.get("schema"),
        effects_count=len(out.get("effects", []) if isinstance(out.get("effects"), list) else []),
        cost_count=len(out.get("cost", []) if isinstance(out.get("cost"), list) else []),
    )
    return out


def extract_and_normalize_skill_rule_data(
    skill_data,
    *,
    skill_id=None,
    strict=PHASE3_STRICT_DEFAULT,
):
    if not isinstance(skill_data, dict):
        return {"schema": SCHEMA_SKILL_RULE_V2, "effects": [], "cost": []}

    source_raw = None
    source_key = None
    for key in SKILL_RULE_SOURCE_KEYS:
        if key not in skill_data:
            continue
        raw = skill_data.get(key)
        if raw in [None, ""]:
            continue
        source_raw = raw
        source_key = key
        break

    if source_raw is None:
        # fallback scan: keep compatibility with legacy sheets embedding JSON in unknown column keys
        for raw in skill_data.values():
            if not isinstance(raw, str):
                continue
            text = raw.strip()
            if not text.startswith("{"):
                continue
            if ('"effects"' not in text) and ('"cost"' not in text) and ('"tags"' not in text):
                continue
            source_raw = raw
            source_key = "embedded_json"
            break

    if source_raw is None:
        row = {"schema": SCHEMA_SKILL_RULE_V2, "effects": [], "cost": []}
        append_audit(
            "extract_skill_rule_data_empty",
            skill_id=str(skill_id or ""),
            strict=bool(strict),
        )
        return row

    source_path = f"skill[{skill_id or '?'}].{source_key or 'rule_data'}"
    try:
        if isinstance(source_raw, dict):
            obj = copy.deepcopy(source_raw)
            # Phase3 strict: persisted JSON strings must declare schema explicitly.
            # Internal in-memory dict fixtures/rules may omit schema, so we inject v2.
            if strict and PHASE3_REQUIRE_SCHEMA and not str(obj.get("schema", "") or "").strip():
                obj["schema"] = SCHEMA_SKILL_RULE_V2
        elif isinstance(source_raw, str):
            obj = _safe_json_object_loads(source_raw, path=source_path)
        else:
            raise JsonRuleV2Error("rule source must be dict or JSON string", path=source_path)
        out = normalize_skill_rule_object(obj, source_path=source_path, strict=strict)
        append_audit(
            "extract_skill_rule_data_ok",
            skill_id=str(skill_id or ""),
            source_key=str(source_key or ""),
            strict=bool(strict),
            schema=out.get("schema"),
        )
        return out
    except JsonRuleV2Error as exc:
        append_audit(
            "extract_skill_rule_data_error",
            skill_id=str(skill_id or ""),
            source_key=str(source_key or ""),
            strict=bool(strict),
            source_path=source_path,
            error=str(exc),
        )
        raise


def normalize_skill_constraints_rows(raw_rows, *, source_path="skill_constraints"):
    if raw_rows is None:
        return []
    if isinstance(raw_rows, dict):
        raw_rows = [raw_rows]
    if not isinstance(raw_rows, list):
        raise JsonRuleV2Error("skill_constraints must be list", path=source_path)

    out = []
    for idx, row in enumerate(raw_rows):
        row_path = f"{source_path}[{idx}]"
        if not isinstance(row, dict):
            raise JsonRuleV2Error("constraint entry must be object", path=row_path)
        normalized = copy.deepcopy(row)
        rule_id = str(normalized.get("id", "") or "").strip()
        if not rule_id:
            rule_id = f"auto:{source_path}:{idx}"
        normalized["id"] = rule_id

        mode = str(normalized.get("mode", "") or "").strip().lower()
        if mode not in {"block", "add_cost"}:
            raise JsonRuleV2Error("mode must be 'block' or 'add_cost'", path=f"{row_path}.mode")
        normalized["mode"] = mode
        normalized["priority"] = _coerce_int(normalized.get("priority", 100), 100)

        match = normalized.get("match", {})
        if match is None:
            match = {}
        if not isinstance(match, dict):
            raise JsonRuleV2Error("match must be object", path=f"{row_path}.match")
        normalized["match"] = match

        if mode == "add_cost":
            add_cost = _normalize_cost_entries(
                normalized.get("add_cost", []),
                path=f"{row_path}.add_cost",
            )
            normalized["add_cost"] = add_cost
        out.append(normalized)

    ids = [str(row.get("id", "")).strip() for row in out]
    dup = {rid for rid in ids if rid and ids.count(rid) > 1}
    if dup:
        append_audit(
            "normalize_skill_constraints_error",
            source_path=source_path,
            error=f"duplicate constraint id(s): {', '.join(sorted(dup))}",
        )
        raise JsonRuleV2Error(
            f"duplicate constraint id(s): {', '.join(sorted(dup))}",
            path=source_path,
        )
    append_audit(
        "normalize_skill_constraints_ok",
        source_path=source_path,
        count=len(out),
    )
    return out
