import copy
import json

from plugins import EFFECT_REGISTRY
from extensions import all_skill_data as GLOBAL_ALL_SKILL_DATA
from manager import skill_effects
from manager import room_manager
from manager.battle import core as battle_core
from manager.battle import duel_solver
from manager.cache_paths import (
    BUFF_CATALOG_CACHE_FILE,
    LEGACY_BUFF_CATALOG_CACHE_FILE,
    LEGACY_SKILLS_CACHE_FILE,
    LEGACY_SUMMON_TEMPLATES_CACHE_FILE,
    SKILLS_CACHE_FILE,
    SUMMON_TEMPLATES_CACHE_FILE,
    load_json_cache,
)
from manager.buff_catalog import get_buff_effect
from manager.game_logic import process_skill_effects


SUPPORTED_EFFECT_TYPES = {
    "APPLY_STATE",
    "APPLY_STATE_PER_N",
    "MULTIPLY_STATE",
    "APPLY_BUFF",
    "GRANT_SKILL",
    "REMOVE_BUFF",
    "DAMAGE_BONUS",
    "MODIFY_ROLL",
    "USE_SKILL_AGAIN",
    "CUSTOM_EFFECT",
    "FORCE_UNOPPOSED",
    "MODIFY_BASE_POWER",
    "MODIFY_FINAL_POWER",
    "DRAIN_HP",
    "SUMMON_CHARACTER",
}

SUPPORTED_EFFECT_TIMINGS = {
    "PRE_MATCH",
    "BEFORE_POWER_ROLL",
    "WIN",
    "LOSE",
    "HIT",
    "UNOPPOSED",
    "AFTER_DAMAGE_APPLY",
    "RESOLVE_START",
    "RESOLVE_STEP_END",
    "RESOLVE_END",
    "END_MATCH",
    "END_ROUND",
    "IMMEDIATE",
    "BATTLE_START",
}

SUPPORTED_TARGETS = {
    "self",
    "target",
    "ALL_ENEMIES",
    "ALL_ALLIES",
    "ALL_OTHER_ALLIES",
    "ALL",
    "NEXT_ALLY",
}

SUPPORTED_CONDITION_SOURCES = {
    "self",
    "target",
    "target_skill",
    "skill",
    "actor_skill",
    "relation",
}

SUPPORTED_CONDITION_OPERATORS = {
    "CONTAINS",
    "GTE",
    "LTE",
    "GT",
    "LT",
    "EQUALS",
}

SUPPORTED_GRANT_MODES = {
    "permanent",
    "duration_rounds",
    "usage_count",
}

SIGNAL_EXPECTED_TYPES = {
    "APPLY_STATE",
    "APPLY_STATE_PER_N",
    "MULTIPLY_STATE",
    "APPLY_BUFF",
    "GRANT_SKILL",
    "REMOVE_BUFF",
    "DAMAGE_BONUS",
    "MODIFY_ROLL",
    "USE_SKILL_AGAIN",
    "CUSTOM_EFFECT",
    "FORCE_UNOPPOSED",
    "MODIFY_BASE_POWER",
    "MODIFY_FINAL_POWER",
    "DRAIN_HP",
    "SUMMON_CHARACTER",
}


def _load_skill_catalog():
    data = load_json_cache(
        SKILLS_CACHE_FILE,
        legacy_paths=[LEGACY_SKILLS_CACHE_FILE],
    )
    assert isinstance(data, dict) and data, "Skill cache is empty or missing."
    return data


def _load_buff_catalog():
    data = load_json_cache(
        BUFF_CATALOG_CACHE_FILE,
        legacy_paths=[LEGACY_BUFF_CATALOG_CACHE_FILE],
    )
    assert isinstance(data, dict), "Buff catalog cache is missing."
    return data


def _load_summon_templates():
    data = load_json_cache(
        SUMMON_TEMPLATES_CACHE_FILE,
        legacy_paths=[LEGACY_SUMMON_TEMPLATES_CACHE_FILE],
    )
    assert isinstance(data, dict), "Summon template cache is missing."
    return data


def _iter_skill_rules(skill_catalog):
    for skill_id, skill_data in skill_catalog.items():
        raw_rule = skill_data.get("特記処理", "")
        if not raw_rule:
            yield skill_id, skill_data, {}
            continue
        try:
            rule_data = json.loads(raw_rule)
        except json.JSONDecodeError as exc:
            yield skill_id, skill_data, exc
            continue
        yield skill_id, skill_data, rule_data


def _sample_lines(lines, limit=8):
    if len(lines) <= limit:
        return lines
    return lines[:limit] + [f"... ({len(lines) - limit} more)"]


class _NoopSocket:
    @staticmethod
    def emit(*_args, **_kwargs):
        return None


def _can_int(v):
    try:
        int(v)
        return True
    except (TypeError, ValueError):
        return False


def _can_float(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _build_char(char_id, name, team, x):
    return {
        "id": char_id,
        "name": name,
        "type": team,
        "hp": 100,
        "maxHp": 100,
        "mp": 50,
        "maxMp": 50,
        "x": x,
        "y": 0,
        "is_escaped": False,
        "params": [
            {"label": "速度", "value": 10},
            {"label": "物理補正", "value": 3},
            {"label": "魔法補正", "value": 3},
        ],
        "states": [
            {"name": "FP", "value": 3},
            {"name": "出血", "value": 0},
            {"name": "亀裂", "value": 0},
            {"name": "破裂", "value": 0},
            {"name": "恐怖", "value": 0},
            {"name": "鈍足", "value": 0},
        ],
        "special_buffs": [],
        "SPassive": [],
        "flags": {},
        "commands": "",
    }


def _set_char_status(char, stat_name, value):
    if stat_name == "HP":
        char["hp"] = int(value)
        return
    if stat_name == "MP":
        char["mp"] = int(value)
        return

    param = next((p for p in char.get("params", []) if p.get("label") == stat_name), None)
    if param is not None:
        param["value"] = int(value)
        return

    state = next((s for s in char.get("states", []) if s.get("name") == stat_name), None)
    if state is None:
        char.setdefault("states", []).append({"name": stat_name, "value": int(value)})
    else:
        state["value"] = int(value)


def _build_trigger_ready_party():
    actor = _build_char("actor_a", "SmokeActor", "ally", 0)
    ally = _build_char("actor_b", "SmokeAlly", "ally", 1)
    target = _build_char("target_a", "SmokeTarget", "enemy", 2)

    for c in (actor, ally, target):
        _set_char_status(c, "FP", 10)
        _set_char_status(c, "出血", 6)
        _set_char_status(c, "亀裂", 7)
        _set_char_status(c, "破裂", 8)
        _set_char_status(c, "荊棘", 4)
        _set_char_status(c, "戦慄", 5)
        _set_char_status(c, "HP", 80)
        _set_char_status(c, "MP", 30)
    return actor, ally, target


def _build_integration_state():
    actor, ally, target = _build_trigger_ready_party()
    return {
        "round": 1,
        "characters": [actor, ally, target],
        "timeline": [
            {"char_id": actor["id"], "speed": 10},
            {"char_id": ally["id"], "speed": 9},
            {"char_id": target["id"], "speed": 8},
        ],
        "battle_state": {},
        "character_owners": {
            actor["id"]: "user_ally",
            ally["id"]: "user_ally",
            target["id"]: "user_enemy",
        },
        "logs": [],
    }


def _stub_update_char_stat(_room, char, name, value, **_kwargs):
    if not isinstance(char, dict):
        return
    try:
        new_val = int(float(value))
    except (TypeError, ValueError):
        new_val = 0

    if name == "HP":
        max_hp = int(char.get("maxHp", 0) or 0)
        if max_hp > 0:
            new_val = min(new_val, max_hp)
        char["hp"] = max(0, new_val)
        if int(char.get("hp", 0)) <= 0:
            char["x"] = -1
            char["y"] = -1
        return

    if name == "MP":
        max_mp = int(char.get("maxMp", 0) or 0)
        if max_mp > 0:
            new_val = min(new_val, max_mp)
        char["mp"] = max(0, new_val)
        return

    _set_char_status(char, name, max(0, new_val))


def _patch_integration_runtime(monkeypatch, state_ref):
    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)
    monkeypatch.setattr(duel_solver, "_update_char_stat", _stub_update_char_stat)
    monkeypatch.setattr(skill_effects, "_update_char_stat", _stub_update_char_stat)

    monkeypatch.setattr(battle_core, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(skill_effects, "broadcast_log", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(battle_core, "socketio", _NoopSocket())
    monkeypatch.setattr(duel_solver, "socketio", _NoopSocket())
    monkeypatch.setattr(room_manager, "socketio", _NoopSocket())

    monkeypatch.setattr(room_manager, "get_room_state", lambda _room: state_ref["value"])
    monkeypatch.setattr(battle_core, "get_room_state", lambda _room: state_ref["value"])
    monkeypatch.setattr(duel_solver, "get_room_state", lambda _room: state_ref["value"])

    monkeypatch.setattr(duel_solver, "save_specific_room_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "broadcast_state_update", lambda *_args, **_kwargs: None)


def _pick_representative_skills_by_effect_type(skill_catalog):
    selected = []
    seen_skill_ids = set()
    for effect_type in sorted(SUPPORTED_EFFECT_TYPES):
        for skill_id, _, rule_data in _iter_skill_rules(skill_catalog):
            if not isinstance(rule_data, dict):
                continue
            effects = rule_data.get("effects", [])
            if not isinstance(effects, list):
                continue
            if any(
                isinstance(e, dict)
                and str(e.get("type", "")).strip() == effect_type
                for e in effects
            ):
                if skill_id not in seen_skill_ids:
                    seen_skill_ids.add(skill_id)
                    selected.append(skill_id)
                break
    return selected


def _prime_effect_for_signal(effect, actor, target):
    effect_type = str(effect.get("type", "")).strip()
    if effect_type == "APPLY_STATE_PER_N":
        source_param = str(effect.get("source_param", "")).strip()
        source = str(effect.get("source", "self")).strip()
        source_char = actor if source == "self" else target
        if source_param:
            _set_char_status(source_char, source_param, 30)

    if effect_type == "MULTIPLY_STATE":
        stat_name = str(effect.get("state_name", "")).strip()
        if stat_name:
            _set_char_status(actor, stat_name, 10)
            _set_char_status(target, stat_name, 10)

    if effect_type == "CUSTOM_EFFECT":
        for c in (actor, target):
            _set_char_status(c, "出血", 6)
            _set_char_status(c, "亀裂", 7)
            _set_char_status(c, "破裂", 8)
            _set_char_status(c, "荊棘", 4)
            _set_char_status(c, "戦慄", 5)

    if effect_type == "DRAIN_HP":
        _set_char_status(actor, "HP", 60)
        _set_char_status(target, "HP", 80)


def _effect_emits_expected_signal(effect, bonus_damage, logs, changes):
    effect_type = str(effect.get("type", "")).strip()
    if effect_type == "DAMAGE_BONUS":
        return int(bonus_damage) > 0
    if effect_type == "MODIFY_ROLL":
        return int(bonus_damage) != 0
    if effect_type == "CUSTOM_EFFECT":
        return bool(changes or logs)
    return bool(changes)


def _lint_condition(skill_id, idx, condition, condition_errors):
    if condition is None:
        return
    if not isinstance(condition, dict):
        condition_errors.append(
            f"{skill_id}[{idx}]: condition must be object, got {type(condition).__name__}"
        )
        return
    source = str(condition.get("source", "")).strip()
    param = str(condition.get("param", "")).strip()
    operator = str(condition.get("operator", "")).strip()

    if not source or source not in SUPPORTED_CONDITION_SOURCES:
        condition_errors.append(f"{skill_id}[{idx}]: invalid condition.source '{source}'")
    if not param:
        condition_errors.append(f"{skill_id}[{idx}]: condition.param is required")
    if operator not in SUPPORTED_CONDITION_OPERATORS:
        condition_errors.append(f"{skill_id}[{idx}]: invalid condition.operator '{operator}'")
    if "value" not in condition:
        condition_errors.append(f"{skill_id}[{idx}]: condition.value is required")


def test_skill_rules_json_and_effect_shape_lint():
    skill_catalog = _load_skill_catalog()
    buff_catalog = _load_buff_catalog()
    summon_templates = _load_summon_templates()
    known_skill_ids = set(skill_catalog.keys())
    known_buff_ids = set(buff_catalog.keys())
    known_buff_names = {str(v.get("name", "")) for v in buff_catalog.values() if isinstance(v, dict)}
    known_custom_effects = set(EFFECT_REGISTRY.keys())
    known_summon_template_ids = set(summon_templates.keys())

    json_errors = []
    shape_errors = []
    field_errors = []
    condition_errors = []
    unknown_type_rows = []
    unknown_timing_rows = []

    for skill_id, skill_data, rule_data in _iter_skill_rules(skill_catalog):
        if isinstance(rule_data, json.JSONDecodeError):
            json_errors.append(
                f"{skill_id}: line={rule_data.lineno} col={rule_data.colno} msg={rule_data.msg}"
            )
            continue

        if not isinstance(rule_data, dict):
            shape_errors.append(f"{skill_id}: rule_data must be object, got {type(rule_data).__name__}")
            continue

        effects = rule_data.get("effects", [])
        if effects in (None, ""):
            effects = []
        if not isinstance(effects, list):
            shape_errors.append(f"{skill_id}: effects must be list, got {type(effects).__name__}")
            continue

        skill_tags = []
        for raw_tags in [skill_data.get("tags", []), rule_data.get("tags", [])]:
            if isinstance(raw_tags, list):
                skill_tags.extend([str(t).strip() for t in raw_tags if str(t).strip()])
        has_instant_tag = any(t in {"即時発動", "instant"} for t in skill_tags)

        for idx, effect in enumerate(effects):
            if not isinstance(effect, dict):
                shape_errors.append(f"{skill_id}[{idx}]: effect must be object, got {type(effect).__name__}")
                continue

            effect_type = str(effect.get("type", "")).strip()
            timing = str(effect.get("timing", "")).strip()
            target = str(effect.get("target", "")).strip()

            if not effect_type:
                shape_errors.append(f"{skill_id}[{idx}]: type is required.")
                continue
            if not timing:
                shape_errors.append(f"{skill_id}[{idx}]: timing is required.")
                continue
            if effect_type not in SUPPORTED_EFFECT_TYPES:
                unknown_type_rows.append(f"{skill_id}[{idx}]: unknown effect type '{effect_type}'")
            if timing not in SUPPORTED_EFFECT_TIMINGS:
                unknown_timing_rows.append(f"{skill_id}[{idx}]: unknown timing '{timing}'")
            if target and target not in SUPPORTED_TARGETS:
                field_errors.append(f"{skill_id}[{idx}]: unsupported target '{target}'")
            if timing == "RESOLVE_START" and has_instant_tag:
                field_errors.append(f"{skill_id}[{idx}]: RESOLVE_START cannot be used with instant tag")

            _lint_condition(skill_id, idx, effect.get("condition"), condition_errors)

            if effect_type == "APPLY_STATE":
                state_name = str(effect.get("state_name", effect.get("name", ""))).strip()
                if not state_name:
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_STATE needs state_name/name")
                if not _can_int(effect.get("value")):
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_STATE value must be int")
            elif effect_type == "APPLY_STATE_PER_N":
                if not str(effect.get("state_name", "")).strip():
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_STATE_PER_N needs state_name")
                if not str(effect.get("source_param", "")).strip():
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_STATE_PER_N needs source_param")
                source = str(effect.get("source", "self")).strip()
                if source not in {"self", "target"}:
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_STATE_PER_N invalid source '{source}'")
                if not _can_int(effect.get("per_N")) or int(effect.get("per_N", 0)) <= 0:
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_STATE_PER_N per_N must be > 0 int")
                if not _can_int(effect.get("value")):
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_STATE_PER_N value must be int")
                if "max_value" in effect and not _can_int(effect.get("max_value")):
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_STATE_PER_N max_value must be int")
            elif effect_type == "MULTIPLY_STATE":
                if not str(effect.get("state_name", "")).strip():
                    field_errors.append(f"{skill_id}[{idx}]: MULTIPLY_STATE needs state_name")
                if not _can_float(effect.get("value")):
                    field_errors.append(f"{skill_id}[{idx}]: MULTIPLY_STATE value must be number")
            elif effect_type == "APPLY_BUFF":
                buff_name = str(effect.get("buff_name", "")).strip()
                buff_id = str(effect.get("buff_id", "")).strip()
                if not buff_name and not buff_id:
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_BUFF needs buff_name or buff_id")
                if buff_id and buff_id not in known_buff_ids:
                    field_errors.append(f"{skill_id}[{idx}]: unknown buff_id '{buff_id}'")
                if buff_name:
                    if buff_name not in known_buff_names and get_buff_effect(buff_name) is None:
                        field_errors.append(f"{skill_id}[{idx}]: unknown buff_name '{buff_name}'")
                if "lasting" in effect and not _can_int(effect.get("lasting")):
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_BUFF lasting must be int")
                if "delay" in effect and not _can_int(effect.get("delay")):
                    field_errors.append(f"{skill_id}[{idx}]: APPLY_BUFF delay must be int")
            elif effect_type == "GRANT_SKILL":
                grant_skill_id = str(effect.get("skill_id", effect.get("grant_skill_id", ""))).strip()
                if not grant_skill_id:
                    field_errors.append(f"{skill_id}[{idx}]: GRANT_SKILL needs skill_id")
                elif grant_skill_id not in known_skill_ids:
                    field_errors.append(f"{skill_id}[{idx}]: GRANT_SKILL unknown skill_id '{grant_skill_id}'")

                grant_mode = str(effect.get("grant_mode", "permanent")).strip()
                if grant_mode not in SUPPORTED_GRANT_MODES:
                    field_errors.append(f"{skill_id}[{idx}]: unsupported grant_mode '{grant_mode}'")
                if "uses" in effect and (not _can_int(effect.get("uses")) or int(effect.get("uses", 0)) <= 0):
                    field_errors.append(f"{skill_id}[{idx}]: GRANT_SKILL uses must be positive int")
                if "duration" in effect and (
                    not _can_int(effect.get("duration")) or int(effect.get("duration", 0)) <= 0
                ):
                    field_errors.append(f"{skill_id}[{idx}]: GRANT_SKILL duration must be positive int")
            elif effect_type == "REMOVE_BUFF":
                if not str(effect.get("buff_name", "")).strip():
                    field_errors.append(f"{skill_id}[{idx}]: REMOVE_BUFF needs buff_name")
            elif effect_type in {"DAMAGE_BONUS", "MODIFY_ROLL", "MODIFY_BASE_POWER", "MODIFY_FINAL_POWER"}:
                if not _can_int(effect.get("value")):
                    field_errors.append(f"{skill_id}[{idx}]: {effect_type} value must be int")
            elif effect_type == "DRAIN_HP":
                if not _can_float(effect.get("value")):
                    field_errors.append(f"{skill_id}[{idx}]: DRAIN_HP value must be number")
            elif effect_type == "CUSTOM_EFFECT":
                custom_name = str(effect.get("value", "")).strip()
                if not custom_name:
                    field_errors.append(f"{skill_id}[{idx}]: CUSTOM_EFFECT value is required")
                elif custom_name not in known_custom_effects:
                    field_errors.append(f"{skill_id}[{idx}]: unknown CUSTOM_EFFECT '{custom_name}'")
            elif effect_type == "USE_SKILL_AGAIN":
                if "max_reuses" in effect and (
                    not _can_int(effect.get("max_reuses")) or int(effect.get("max_reuses", 0)) <= 0
                ):
                    field_errors.append(f"{skill_id}[{idx}]: USE_SKILL_AGAIN max_reuses must be positive int")
                reuse_cost = effect.get("reuse_cost")
                if reuse_cost is not None and not isinstance(reuse_cost, (list, dict)):
                    field_errors.append(f"{skill_id}[{idx}]: reuse_cost must be list or dict")
            elif effect_type == "SUMMON_CHARACTER":
                template_id = str(
                    effect.get("summon_template_id")
                    or effect.get("template_id")
                    or effect.get("summon_id")
                    or ""
                ).strip()
                if not template_id:
                    field_errors.append(f"{skill_id}[{idx}]: SUMMON_CHARACTER needs summon_template_id")
                elif template_id not in known_summon_template_ids:
                    field_errors.append(f"{skill_id}[{idx}]: unknown summon_template_id '{template_id}'")

    failures = []
    if json_errors:
        failures.extend(["JSON parse errors:"] + _sample_lines(json_errors))
    if shape_errors:
        failures.extend(["Shape errors:"] + _sample_lines(shape_errors))
    if field_errors:
        failures.extend(["Field errors:"] + _sample_lines(field_errors, limit=20))
    if condition_errors:
        failures.extend(["Condition errors:"] + _sample_lines(condition_errors, limit=20))
    if unknown_type_rows:
        failures.extend(["Unknown effect types:"] + _sample_lines(unknown_type_rows))
    if unknown_timing_rows:
        failures.extend(["Unknown timings:"] + _sample_lines(unknown_timing_rows))

    assert not failures, "Skill lint failed:\n" + "\n".join(failures)


def test_skill_effects_smoke_all_timings(monkeypatch):
    skill_catalog = _load_skill_catalog()
    room_state_ref = {"value": None}
    monkeypatch.setattr(room_manager, "get_room_state", lambda _room: room_state_ref["value"])

    failures = []

    for skill_id, _, rule_data in _iter_skill_rules(skill_catalog):
        if not isinstance(rule_data, dict):
            continue
        effects = rule_data.get("effects", [])
        if not isinstance(effects, list) or not effects:
            continue

        timings = sorted(
            {
                str(effect.get("timing", "")).strip()
                for effect in effects
                if isinstance(effect, dict) and str(effect.get("timing", "")).strip()
            }
        )
        if not timings:
            continue

        for timing in timings:
            actor = _build_char("actor_a", "SmokeActor", "ally", 0)
            ally = _build_char("actor_b", "SmokeAlly", "ally", 1)
            target = _build_char("target_a", "SmokeTarget", "enemy", 2)

            room_state = {
                "characters": [actor, ally, target],
                "timeline": [actor["id"], ally["id"], target["id"]],
                "battle_state": {
                    "slots": {
                        "slot_a": {"actor_id": actor["id"], "initiative": 10},
                        "slot_b": {"actor_id": ally["id"], "initiative": 9},
                        "slot_t": {"actor_id": target["id"], "initiative": 8},
                    }
                },
            }
            room_state_ref["value"] = room_state
            context = {
                "room": "skill_smoke_room",
                "characters": room_state["characters"],
                "timeline": [
                    {"char_id": actor["id"], "speed": 10},
                    {"char_id": ally["id"], "speed": 9},
                    {"char_id": target["id"], "speed": 8},
                ],
                "battle_state": room_state["battle_state"],
            }

            try:
                process_skill_effects(
                    copy.deepcopy(effects),
                    timing,
                    actor,
                    target,
                    target_skill_data={"tags": ["守備", "防御"]},
                    context=context,
                    base_damage=12,
                )
            except Exception as exc:  # pragma: no cover - only for smoke aggregation
                failures.append(f"{skill_id}@{timing}: {type(exc).__name__}: {exc}")

    assert not failures, "Skill smoke failures:\n" + "\n".join(_sample_lines(failures, limit=20))


def test_unconditional_effects_emit_signal():
    skill_catalog = _load_skill_catalog()
    failures = []

    for skill_id, _, rule_data in _iter_skill_rules(skill_catalog):
        if not isinstance(rule_data, dict):
            continue
        effects = rule_data.get("effects", [])
        if not isinstance(effects, list) or not effects:
            continue

        for idx, raw_effect in enumerate(effects):
            if not isinstance(raw_effect, dict):
                continue
            if raw_effect.get("condition"):
                continue

            effect_type = str(raw_effect.get("type", "")).strip()
            timing = str(raw_effect.get("timing", "")).strip()
            if effect_type not in SIGNAL_EXPECTED_TYPES:
                continue
            if not timing:
                continue

            effect = copy.deepcopy(raw_effect)
            actor, ally, target = _build_trigger_ready_party()
            _prime_effect_for_signal(effect, actor, target)

            room_state = {
                "characters": [actor, ally, target],
                "timeline": [actor["id"], ally["id"], target["id"]],
                "battle_state": {
                    "slots": {
                        "slot_a": {"actor_id": actor["id"], "initiative": 10},
                        "slot_b": {"actor_id": ally["id"], "initiative": 9},
                        "slot_t": {"actor_id": target["id"], "initiative": 8},
                    }
                },
            }
            context = {
                "room": "skill_smoke_room",
                "characters": room_state["characters"],
                "timeline": [
                    {"char_id": actor["id"], "speed": 10},
                    {"char_id": ally["id"], "speed": 9},
                    {"char_id": target["id"], "speed": 8},
                ],
                "battle_state": room_state["battle_state"],
            }

            try:
                bonus_damage, logs, changes = process_skill_effects(
                    [effect],
                    timing,
                    actor,
                    target,
                    target_skill_data={"tags": ["守備", "防御"]},
                    context=context,
                    base_damage=12,
                )
            except Exception as exc:  # pragma: no cover - only for aggregation
                failures.append(f"{skill_id}[{idx}] {effect_type}: {type(exc).__name__}: {exc}")
                continue

            if not _effect_emits_expected_signal(effect, bonus_damage, logs, changes):
                failures.append(
                    f"{skill_id}[{idx}] {effect_type}: produced no signal "
                    f"(bonus={bonus_damage}, logs={len(logs)}, changes={len(changes)})"
                )

    assert not failures, "Unconditional effect signal failures:\n" + "\n".join(_sample_lines(failures, limit=25))


def test_select_resolve_one_sided_integration_smoke(monkeypatch):
    skill_catalog = _load_skill_catalog()
    state_ref = {"value": None}
    _patch_integration_runtime(monkeypatch, state_ref)

    backup = dict(GLOBAL_ALL_SKILL_DATA)
    GLOBAL_ALL_SKILL_DATA.clear()
    GLOBAL_ALL_SKILL_DATA.update(skill_catalog)

    failures = []
    defender_skill_data = skill_catalog.get("D-00") or next(iter(skill_catalog.values()))

    try:
        for skill_id, attacker_skill_data in sorted(skill_catalog.items()):
            state = _build_integration_state()
            state_ref["value"] = state
            actor = state["characters"][0]
            target = state["characters"][2]

            try:
                res = battle_core._resolve_one_sided_by_existing_logic(
                    room="skill_smoke_room",
                    state=state,
                    attacker_char=actor,
                    defender_char=target,
                    attacker_skill_data=copy.deepcopy(attacker_skill_data),
                    defender_skill_data=copy.deepcopy(defender_skill_data),
                )
            except Exception as exc:  # pragma: no cover - smoke aggregation
                failures.append(f"{skill_id}: exception {type(exc).__name__}: {exc}")
                continue

            if not isinstance(res, dict) or not res.get("ok", False):
                failures.append(f"{skill_id}: not ok -> {res}")
    finally:
        GLOBAL_ALL_SKILL_DATA.clear()
        GLOBAL_ALL_SKILL_DATA.update(backup)

    assert not failures, "Select/Resolve one-sided smoke failures:\n" + "\n".join(_sample_lines(failures, limit=25))


def test_select_resolve_clash_integration_representative(monkeypatch):
    skill_catalog = _load_skill_catalog()
    state_ref = {"value": None}
    _patch_integration_runtime(monkeypatch, state_ref)

    representative_skill_ids = _pick_representative_skills_by_effect_type(skill_catalog)
    assert representative_skill_ids, "No representative skills found."

    backup = dict(GLOBAL_ALL_SKILL_DATA)
    GLOBAL_ALL_SKILL_DATA.clear()
    GLOBAL_ALL_SKILL_DATA.update(skill_catalog)

    failures = []
    defender_skill_data = skill_catalog.get("D-00") or next(iter(skill_catalog.values()))

    try:
        for skill_id in representative_skill_ids:
            attacker_skill_data = skill_catalog.get(skill_id)
            if not isinstance(attacker_skill_data, dict):
                continue

            state = _build_integration_state()
            state_ref["value"] = state
            actor = state["characters"][0]
            target = state["characters"][2]

            try:
                res = battle_core._resolve_clash_by_existing_logic(
                    room="skill_smoke_room",
                    state=state,
                    attacker_char=actor,
                    defender_char=target,
                    attacker_skill_data=copy.deepcopy(attacker_skill_data),
                    defender_skill_data=copy.deepcopy(defender_skill_data),
                )
            except Exception as exc:  # pragma: no cover - smoke aggregation
                failures.append(f"{skill_id}: exception {type(exc).__name__}: {exc}")
                continue

            if not isinstance(res, dict) or not res.get("ok", False):
                failures.append(f"{skill_id}: not ok -> {res}")
    finally:
        GLOBAL_ALL_SKILL_DATA.clear()
        GLOBAL_ALL_SKILL_DATA.update(backup)

    assert not failures, "Select/Resolve clash smoke failures:\n" + "\n".join(_sample_lines(failures, limit=25))
