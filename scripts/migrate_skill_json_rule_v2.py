import argparse
import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from manager.buff_catalog import get_buff_by_id
from manager.json_rule_v2 import (
    JsonRuleV2Error,
    extract_and_normalize_skill_rule_data,
    normalize_skill_constraints_rows,
)


DEFAULT_SKILLS = REPO_ROOT / "data" / "cache" / "skills_cache.json"
DEFAULT_BUFFS = REPO_ROOT / "data" / "cache" / "buff_catalog_cache.json"
DEFAULT_STAGE_PRESETS = REPO_ROOT / "data" / "cache" / "battle_only_presets_cache.json"
DEFAULT_OUTDIR = REPO_ROOT / "logs" / "migration_v2"


_DYNAMIC_NAME_PATTERNS = [
    (re.compile(r"^(.*)_Atk(\d+)$"), "Bu-32", +1),
    (re.compile(r"^(.*)_Def(\d+)$"), "Bu-33", +1),
    (re.compile(r"^(.*)_AtkDown(\d+)$"), "Bu-34", -1),
    (re.compile(r"^(.*)_DefDown(\d+)$"), "Bu-35", -1),
    (re.compile(r"^(.*)_Phys(\d+)$"), "Bu-36", +1),
    (re.compile(r"^(.*)_PhysDown(\d+)$"), "Bu-37", -1),
    (re.compile(r"^(.*)_Mag(\d+)$"), "Bu-38", +1),
    (re.compile(r"^(.*)_MagDown(\d+)$"), "Bu-39", -1),
    (re.compile(r"^(.*)_Crack(\d+)$"), "Bu-40", +1),
    (re.compile(r"^(.*)_CrackOnce(\d+)$"), "Bu-41", +1),
    (re.compile(r"^(.*)_Act(\d+)$"), "Bu-42", +1),
    (re.compile(r"^(.*)_DaIn(\d+)$"), "Bu-43", +1),
    (re.compile(r"^(.*)_DaCut(\d+)$"), "Bu-44", +1),
    (re.compile(r"^(.*)_DaOut(\d+)$"), "Bu-45", +1),
    (re.compile(r"^(.*)_DaOutDown(\d+)$"), "Bu-46", +1),
    (re.compile(r"^(.*)_BleedReact(\d+)$"), "Bu-47", +1),
]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _build_name_to_id_map(buff_catalog):
    out = {}
    if not isinstance(buff_catalog, dict):
        return out
    for buff_id, row in buff_catalog.items():
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "") or "").strip()
        if name:
            out[name] = str(buff_id)
    return out


def _resolve_dynamic_buff_name(name):
    text = str(name or "").strip()
    if not text:
        return None
    for pattern, buff_id, sign in _DYNAMIC_NAME_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        raw_value = _safe_int(m.group(2))
        if raw_value is None:
            return None
        return {"buff_id": buff_id, "value": raw_value * sign}
    return None


def _resolve_buff_ref(buff_name, name_to_id):
    name = str(buff_name or "").strip()
    if not name:
        return None
    buff_id = name_to_id.get(name)
    if buff_id:
        return {"buff_id": buff_id, "value": None}
    return _resolve_dynamic_buff_name(name)


def _migrate_effect_rows(rule_obj, name_to_id, report, skill_id):
    effects = rule_obj.get("effects", [])
    if not isinstance(effects, list):
        return
    for idx, row in enumerate(effects):
        if not isinstance(row, dict):
            continue
        e_type = str(row.get("type", "")).strip().upper()
        if e_type not in {"APPLY_BUFF", "REMOVE_BUFF"}:
            continue

        buff_id = str(row.get("buff_id", "") or "").strip()
        buff_name = str(row.get("buff_name", "") or "").strip()
        if buff_id:
            continue
        if not buff_name:
            report["errors"].append(
                {
                    "resource": "skills",
                    "id": skill_id,
                    "path": f"effects[{idx}]",
                    "error": "APPLY/REMOVE_BUFF requires buff_id or buff_name",
                }
            )
            continue

        resolved = _resolve_buff_ref(buff_name, name_to_id)
        if not resolved:
            report["errors"].append(
                {
                    "resource": "skills",
                    "id": skill_id,
                    "path": f"effects[{idx}].buff_name",
                    "error": f"cannot resolve buff_id from buff_name '{buff_name}'",
                }
            )
            continue

        row["buff_id"] = resolved["buff_id"]
        if e_type == "APPLY_BUFF" and resolved["value"] is not None:
            data = row.get("data")
            if not isinstance(data, dict):
                data = {}
                row["data"] = data
            current = _safe_int(data.get("value"))
            if current is None:
                data["value"] = int(resolved["value"])
            elif current != int(resolved["value"]):
                report["errors"].append(
                    {
                        "resource": "skills",
                        "id": skill_id,
                        "path": f"effects[{idx}].data.value",
                        "error": f"value mismatch: dynamic({resolved['value']}) != data.value({current})",
                    }
                )


def migrate_skills(skills_data, buff_catalog, report):
    out = {}
    name_to_id = _build_name_to_id_map(buff_catalog)
    if not isinstance(skills_data, dict):
        report["errors"].append({"resource": "skills", "id": "-", "path": "$", "error": "skills root must be object"})
        return out

    for skill_id, row in skills_data.items():
        if not isinstance(row, dict):
            out[skill_id] = row
            continue
        item = copy.deepcopy(row)
        try:
            rule = extract_and_normalize_skill_rule_data(item, skill_id=skill_id, strict=False)
            _migrate_effect_rows(rule, name_to_id, report, skill_id)
            rule["schema"] = "skill_json_rule_v2"
            item["rule_data"] = rule
            item["特記処理"] = json.dumps(rule, ensure_ascii=False, separators=(",", ":"))
            report["migrated"]["skills"] += 1
        except JsonRuleV2Error as ex:
            report["errors"].append(
                {
                    "resource": "skills",
                    "id": str(skill_id),
                    "path": getattr(ex, "path", ""),
                    "error": str(ex),
                }
            )
            report["failed"]["skills"] += 1
        out[skill_id] = item
    return out


def migrate_buff_catalog(buff_data, report):
    out = {}
    if not isinstance(buff_data, dict):
        report["errors"].append({"resource": "buff_catalog", "id": "-", "path": "$", "error": "buff root must be object"})
        return out
    for buff_id, row in buff_data.items():
        if not isinstance(row, dict):
            out[buff_id] = row
            continue
        item = copy.deepcopy(row)
        item["id"] = str(item.get("id") or buff_id)
        name = str(item.get("name", "") or "").strip()
        if not name:
            report["errors"].append(
                {"resource": "buff_catalog", "id": str(buff_id), "path": "name", "error": "missing buff name"}
            )
            report["failed"]["buff_catalog"] += 1
        else:
            report["migrated"]["buff_catalog"] += 1
        if not str(item.get("display_name", "") or "").strip():
            item["display_name"] = name
        effect = item.get("effect")
        if not isinstance(effect, dict):
            item["effect"] = {}
        out[buff_id] = item
    return out


def _migrate_stage_profile(profile, report, stage_id):
    if not isinstance(profile, dict):
        return profile
    out = copy.deepcopy(profile)
    rules = out.get("rules")
    if not isinstance(rules, list):
        return out
    new_rules = []
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            new_rules.append(rule)
            continue
        row = copy.deepcopy(rule)
        constraints = row.get("skill_constraints", None)
        if constraints is None and isinstance(row.get("rule"), dict):
            constraints = row.get("rule", {}).get("skill_constraints")
        if constraints is not None:
            try:
                row["skill_constraints"] = normalize_skill_constraints_rows(
                    constraints,
                    source_path=f"stage_presets[{stage_id}].field_effect_profile.rules[{idx}].skill_constraints",
                )
                report["migrated"]["field_effects"] += 1
            except JsonRuleV2Error as ex:
                report["errors"].append(
                    {
                        "resource": "field_effects",
                        "id": str(stage_id),
                        "path": getattr(ex, "path", ""),
                        "error": str(ex),
                    }
                )
                report["failed"]["field_effects"] += 1
        new_rules.append(row)
    out["rules"] = new_rules
    return out


def migrate_stage_presets(stage_data, report):
    if not isinstance(stage_data, dict):
        report["errors"].append({"resource": "field_effects", "id": "-", "path": "$", "error": "preset root must be object"})
        return stage_data
    out = copy.deepcopy(stage_data)
    stage_presets = out.get("stage_presets")
    if not isinstance(stage_presets, dict):
        return out
    for stage_id, row in stage_presets.items():
        if not isinstance(row, dict):
            continue
        profile = row.get("field_effect_profile")
        if profile is None:
            continue
        row["field_effect_profile"] = _migrate_stage_profile(profile, report, stage_id)
    return out


def run(args):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.output_dir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp": ts,
        "schema": "skill_json_rule_v2",
        "migrated": {"skills": 0, "buff_catalog": 0, "field_effects": 0},
        "failed": {"skills": 0, "buff_catalog": 0, "field_effects": 0},
        "errors": [],
        "outputs": {},
    }

    skills_data = _load_json(Path(args.skills))
    buff_data = _load_json(Path(args.buffs))
    stage_data = _load_json(Path(args.stage_presets))

    migrated_buffs = migrate_buff_catalog(buff_data, report)
    migrated_skills = migrate_skills(skills_data, migrated_buffs, report)
    migrated_stage = migrate_stage_presets(stage_data, report)

    out_skills = outdir / f"skills_cache.v2.{ts}.json"
    out_buffs = outdir / f"buff_catalog_cache.v2.{ts}.json"
    out_stage = outdir / f"battle_only_presets_cache.v2.{ts}.json"
    out_report = outdir / f"migration_report.{ts}.json"

    _dump_json(out_skills, migrated_skills)
    _dump_json(out_buffs, migrated_buffs)
    _dump_json(out_stage, migrated_stage)
    _dump_json(out_report, report)

    report["outputs"] = {
        "skills": str(out_skills),
        "buff_catalog": str(out_buffs),
        "stage_presets": str(out_stage),
        "report": str(out_report),
    }
    _dump_json(out_report, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def build_argparser():
    p = argparse.ArgumentParser(description="Migrate cache JSON resources to skill_json_rule_v2.")
    p.add_argument("--skills", default=str(DEFAULT_SKILLS))
    p.add_argument("--buffs", default=str(DEFAULT_BUFFS))
    p.add_argument("--stage-presets", default=str(DEFAULT_STAGE_PRESETS))
    p.add_argument("--output-dir", default=str(DEFAULT_OUTDIR))
    return p


if __name__ == "__main__":
    raise SystemExit(run(build_argparser().parse_args()))
