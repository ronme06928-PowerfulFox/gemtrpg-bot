from __future__ import annotations

import csv
import json
import os
from copy import deepcopy
from io import StringIO

import requests

from manager.cache_paths import (
    SUMMON_TEMPLATES_CACHE_FILE,
    LEGACY_SUMMON_TEMPLATES_CACHE_FILE,
    load_json_cache,
    save_json_cache,
)
from manager.logs import setup_logger

logger = setup_logger(__name__)

SUMMON_TEMPLATES_CSV_URL = os.environ.get(
    "SUMMON_TEMPLATES_CSV_URL",
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTkulkkIx6AQEHBKJiAqnjyzEQX5itUVV3SDwi40sLmXeiVQbXvg0RmMS3-"
    "XLSwNo2YHsF3WybyHjMu/pub?gid=358283359&single=true&output=csv",
)


def _pick(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row and row[key] is not None:
            return str(row[key]).strip()
    return ""


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _split_csv_list(value: str):
    if value is None:
        return []
    normalized = str(value).replace("、", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def _parse_inventory(raw_value: str):
    raw = str(raw_value or "").strip()
    if not raw:
        return {}

    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                out = {}
                for key, value in parsed.items():
                    item_id = str(key or "").strip()
                    if not item_id:
                        continue
                    out[item_id] = max(0, _safe_int(value, 0))
                return out
        except Exception:
            pass

    out = {}
    for token in _split_csv_list(raw):
        if ":" in token:
            item_id, count_str = token.split(":", 1)
            item_id = item_id.strip()
            if not item_id:
                continue
            out[item_id] = max(0, _safe_int(count_str, 1))
            continue
        out[token] = 1
    return out


def _merge_param_list(base_params, override_params):
    merged = []
    seen = set()
    for src in [base_params, override_params]:
        if not isinstance(src, list):
            continue
        for row in src:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label", "")).strip()
            if not label:
                continue
            if label in seen:
                for i, existing in enumerate(merged):
                    if existing.get("label") == label:
                        merged[i] = {"label": label, "value": row.get("value", "0")}
                        break
                continue
            merged.append({"label": label, "value": row.get("value", "0")})
            seen.add(label)
    return merged


def _parse_duration(value):
    n = _safe_int(value, -1)
    if n == -1:
        return "permanent", 0
    if n <= 0:
        return "duration_rounds", 1
    return "duration_rounds", n


def _parse_allow_duplicate(value, default=True):
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    if text in {"1", "true", "yes", "y", "on", "ok", "allow", "可"}:
        return True
    if text in {"0", "false", "no", "n", "off", "ng", "deny", "不可"}:
        return False
    return bool(default)


def _parse_extra_json(raw: str, template_id: str):
    data = {}
    raw_text = str(raw or "").strip()
    if not raw_text:
        return data
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.warning("summon template %s: invalid 特記JSON: %s", template_id, e)
        return {}
    if not isinstance(data, dict):
        logger.warning("summon template %s: 特記JSON is not object", template_id)
        return {}
    return data


def _build_row_template(row: dict):
    template_id = _pick(row, "ユニットID", "template_id", "id")
    if not template_id:
        return None, None

    extra = _parse_extra_json(_pick(row, "特記JSON", "extra_json"), template_id)
    mode, duration = _parse_duration(_pick(row, "持続設定", "duration", "summon_duration"))
    allow_duplicate = _parse_allow_duplicate(
        _pick(row, "重複", "duplicate", "allow_duplicate"),
        default=extra.get("allow_duplicate_same_team", extra.get("allow_duplicate", True)),
    )

    hp = _safe_int(_pick(row, "HP", "hp"), _safe_int(extra.get("hp", 1), 1))
    max_hp = max(1, _safe_int(_pick(row, "最大HP", "max_hp", "maxHp"), _safe_int(extra.get("maxHp", hp), hp)))
    hp = min(max_hp, max(0, hp))

    mp = _safe_int(_pick(row, "MP", "mp"), _safe_int(extra.get("mp", 0), 0))
    max_mp = max(0, _safe_int(_pick(row, "最大MP", "max_mp", "maxMp"), _safe_int(extra.get("maxMp", mp), mp)))
    mp = min(max_mp, max(0, mp))

    speed = _safe_int(_pick(row, "速度", "speed"), 0)
    phys_mod = _safe_int(_pick(row, "物理補正", "physical_modifier"), 0)
    magic_mod = _safe_int(_pick(row, "魔法補正", "magic_modifier"), 0)
    override_params = [
        {"label": "速度", "value": str(speed)},
        {"label": "物理補正", "value": str(phys_mod)},
        {"label": "魔法補正", "value": str(magic_mod)},
    ]
    params = _merge_param_list(extra.get("params", []), override_params)

    template = dict(extra)
    template["baseName"] = template_id
    template["name"] = _pick(row, "表示名", "name") or str(extra.get("name") or template_id)
    template["hp"] = hp
    template["maxHp"] = max_hp
    template["mp"] = mp
    template["maxMp"] = max_mp
    template["initial_skill_ids"] = _split_csv_list(_pick(row, "戦闘スキル", "initial_skill_ids"))
    template["SPassive"] = _split_csv_list(_pick(row, "パッシブスキル", "SPassive"))
    template["radiance_skills"] = _split_csv_list(_pick(row, "輝化スキル", "radiance_skills"))
    template["hidden_skills"] = _split_csv_list(_pick(row, "秘匿スキル", "hidden_skills"))
    template["inventory"] = _parse_inventory(_pick(row, "所持アイテム", "inventory"))
    template["summon_duration_mode"] = mode
    template["summon_duration"] = duration
    template["allow_duplicate_same_team"] = bool(allow_duplicate)
    template["params"] = params
    return template_id, template


def fetch_summon_templates_from_csv():
    logger.info("summon templates csv fetch: %s", SUMMON_TEMPLATES_CSV_URL)
    try:
        response = requests.get(SUMMON_TEMPLATES_CSV_URL, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
    except Exception as e:
        logger.error("summon templates csv fetch failed: %s", e)
        return {}

    reader = csv.DictReader(StringIO(response.text))
    templates = {}
    for raw_row in reader:
        row = {}
        for key, value in (raw_row or {}).items():
            clean_key = str(key or "").replace("\ufeff", "").strip()
            row[clean_key] = str(value or "").strip()
        template_id, template = _build_row_template(row)
        if not template_id or not isinstance(template, dict):
            continue
        templates[template_id] = template
    logger.info("summon templates csv parsed: %s entries", len(templates))
    return templates


def refresh_summon_templates():
    templates = fetch_summon_templates_from_csv()
    if templates:
        save_json_cache(SUMMON_TEMPLATES_CACHE_FILE, templates)
    return templates


def load_summon_templates(force_refresh: bool = False):
    if force_refresh:
        data = refresh_summon_templates()
    else:
        data = load_json_cache(
            SUMMON_TEMPLATES_CACHE_FILE,
            legacy_paths=[LEGACY_SUMMON_TEMPLATES_CACHE_FILE],
        ) or {}
        if not data:
            data = refresh_summon_templates()
    if not isinstance(data, dict):
        logger.warning("summon templates cache is not dict: %s", type(data))
        return {}
    return data


def get_summon_template(template_id: str):
    if not template_id:
        return None
    templates = load_summon_templates()
    tpl = templates.get(template_id)
    if not isinstance(tpl, dict):
        return None
    return deepcopy(tpl)
