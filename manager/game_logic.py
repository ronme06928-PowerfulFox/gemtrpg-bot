# manager/game_logic.py
import sys
import json
import re # Added for regex
from manager.battle.system_skills import ensure_system_skills_registered
from manager.buff_catalog import get_buff_effect, resolve_runtime_buff_effect
from manager.field_effects import (
    get_state_from_context,
    get_stage_damage_dealt_mod,
    get_stage_state_effects,
)
from manager.logs import setup_logger

logger = setup_logger(__name__)
ensure_system_skills_registered()


def _utils_module():
    return sys.modules.get('manager.utils')


def _effect_registry():
    plugins_mod = sys.modules.get("plugins")
    if plugins_mod is None:
        try:
            import plugins as plugins_mod  # type: ignore
        except Exception:
            return {}
    registry = getattr(plugins_mod, "EFFECT_REGISTRY", None)
    return registry if isinstance(registry, dict) else {}


def _fallback_get_status_value(char_obj, status_name):
    if not isinstance(char_obj, dict):
        return 0
    if status_name in ("HP", "hp"):
        return int(char_obj.get("hp", 0) or 0)
    if status_name in ("MP", "mp"):
        return int(char_obj.get("mp", 0) or 0)
    states = char_obj.get("states", [])
    if isinstance(states, list):
        hit = next((s for s in states if isinstance(s, dict) and s.get("name") == status_name), None)
        if isinstance(hit, dict):
            try:
                return int(hit.get("value", 0))
            except Exception:
                return 0
    return int(char_obj.get(status_name, 0) or 0)


_STATE_STACK_SUM_KEYS = {
    "状態異常スタック合計",
    "状態異常合算",
    "status_stack_sum",
    "status_stack_total",
    "debuff_stack_sum",
}


def _normalize_condition_status_name(status_name):
    text = str(status_name or "").strip()
    if not text:
        return ""
    mod = _utils_module()
    fn = getattr(mod, "normalize_status_name", None) if mod else None
    if callable(fn):
        try:
            normalized = fn(text)
            if normalized:
                return str(normalized).strip()
        except Exception:
            pass
    return text


def _parse_state_stack_sum_param(param_name):
    raw = str(param_name or "").strip()
    if not raw:
        return None

    m = re.match(r"^(.+?)\s*[:：]\s*(.+)$", raw)
    if not m:
        return None

    key = str(m.group(1) or "").strip().lower()
    if key not in {k.lower() for k in _STATE_STACK_SUM_KEYS}:
        return None

    names_raw = str(m.group(2) or "").strip()
    if not names_raw:
        return None

    names = set()
    for token in re.split(r"[,\s、，/|・]+", names_raw):
        normalized = _normalize_condition_status_name(token)
        if normalized:
            names.add(normalized)
    return names if names else None


def _resolve_state_stack_sum_value(char_obj, param_name):
    if not isinstance(char_obj, dict):
        return None

    target_names = _parse_state_stack_sum_param(param_name)
    if target_names is None:
        return None

    total = 0
    states = char_obj.get("states", [])
    if not isinstance(states, list):
        return 0

    for row in states:
        if not isinstance(row, dict):
            continue
        state_name = _normalize_condition_status_name(row.get("name"))
        if state_name not in target_names:
            continue
        try:
            value = int(row.get("value", 0) or 0)
        except Exception:
            value = 0
        if value > 0:
            total += value

    return total


def _stable_get_status_value(char_obj, status_name):
    state_stack_sum = _resolve_state_stack_sum_value(char_obj, status_name)
    if state_stack_sum is not None:
        return state_stack_sum

    mod = _utils_module()
    fn = getattr(mod, "get_status_value", None) if mod else None
    if callable(fn):
        try:
            primary = fn(char_obj, status_name)
        except Exception:
            primary = None
        fallback = _fallback_get_status_value(char_obj, status_name)
        try:
            primary_int = int(primary)
        except Exception:
            primary_int = primary
        # Prefer fallback only when the injected helper misses existing state/param values.
        if primary is None:
            return fallback
        if isinstance(primary_int, int) and primary_int == 0 and fallback != 0:
            return fallback
        return primary_int
    return _fallback_get_status_value(char_obj, status_name)


def get_status_value(char_obj, status_name):
    return _stable_get_status_value(char_obj, status_name)


def _stable_set_status_value(char_obj, status_name, value):
    mod = _utils_module()
    fn = getattr(mod, "set_status_value", None) if mod else None
    if callable(fn):
        try:
            result = fn(char_obj, status_name, value)
        except Exception:
            result = None
        if status_name in ("HP", "hp"):
            char_obj["hp"] = int(value or 0)
            return result
        if status_name in ("MP", "mp"):
            char_obj["mp"] = int(value or 0)
            return result

        expected = int(value or 0)
        states = char_obj.get("states", [])
        if not isinstance(states, list):
            states = []
            char_obj["states"] = states
        hit = next((s for s in states if isinstance(s, dict) and s.get("name") == status_name), None)
        if hit is None:
            states.append({"name": status_name, "value": expected})
        else:
            try:
                current = int(hit.get("value", 0) or 0)
            except Exception:
                current = None
            if current != expected:
                hit["value"] = expected
        return result
    if not isinstance(char_obj, dict):
        return None
    if status_name in ("HP", "hp"):
        char_obj["hp"] = int(value or 0)
        return None
    if status_name in ("MP", "mp"):
        char_obj["mp"] = int(value or 0)
        return None
    states = char_obj.setdefault("states", [])
    if not isinstance(states, list):
        states = []
        char_obj["states"] = states
    hit = next((s for s in states if isinstance(s, dict) and s.get("name") == status_name), None)
    if hit is None:
        states.append({"name": status_name, "value": int(value or 0)})
    else:
        hit["value"] = int(value or 0)
    return None


def set_status_value(char_obj, status_name, value):
    return _stable_set_status_value(char_obj, status_name, value)


def apply_buff(*args, **kwargs):
    mod = _utils_module()
    fn = getattr(mod, "apply_buff", None) if mod else None
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def remove_buff(*args, **kwargs):
    mod = _utils_module()
    fn = getattr(mod, "remove_buff", None) if mod else None
    if callable(fn):
        return fn(*args, **kwargs)
    # Fallback: manager.utils 未ロード時でも最低限の削除を行う。
    try:
        char_obj = args[0] if len(args) >= 1 else kwargs.get("char_obj")
        buff_name = args[1] if len(args) >= 2 else kwargs.get("buff_name")
        if not isinstance(char_obj, dict):
            return None
        buffs = char_obj.get("special_buffs")
        if not isinstance(buffs, list):
            return None
        normalized_name = str(buff_name or "").strip()
        char_obj["special_buffs"] = [
            b for b in buffs
            if str((b or {}).get("name", "")).strip() != normalized_name
        ]
    except Exception:
        return None
    return None


def get_buff_stat_mod(char_obj, stat_name):
    mod = _utils_module()
    fn = getattr(mod, "get_buff_stat_mod", None) if mod else None
    if callable(fn):
        return fn(char_obj, stat_name)
    return 0


def get_buff_stat_mod_details(char_obj, stat_name):
    mod = _utils_module()
    fn = getattr(mod, "get_buff_stat_mod_details", None) if mod else None
    if callable(fn):
        return fn(char_obj, stat_name)
    return []


def resolve_placeholders(text, char_obj):
    mod = _utils_module()
    fn = getattr(mod, "resolve_placeholders", None) if mod else None
    if callable(fn):
        return fn(text, char_obj)
    return text


def get_effective_origin_id(char_obj):
    mod = _utils_module()
    fn = getattr(mod, "get_effective_origin_id", None) if mod else None
    if callable(fn):
        return fn(char_obj)
    return 0


def compute_origin_skill_modifiers(actor_char, target_char, skill_data, state=None, context=None):
    mod = _utils_module()
    fn = getattr(mod, "compute_origin_skill_modifiers", None) if mod else None
    if callable(fn):
        return fn(actor_char, target_char, skill_data, state=state, context=context)
    return {}


def build_origin_hit_changes(actor_char, target_char, context=None):
    mod = _utils_module()
    fn = getattr(mod, "build_origin_hit_changes", None) if mod else None
    if callable(fn):
        return fn(actor_char, target_char, context=context)
    return [], []

def _canonical_team(value):
    text = str(value or "").strip().lower()
    if text in {"ally", "friend", "friends", "player"}:
        return "ally"
    if text in {"enemy", "foe", "opponent", "npc", "boss"}:
        return "enemy"
    return text


def _normalize_buff_name_for_condition(name):
    raw = str(name or "").strip()
    if not raw:
        return raw
    mod = _utils_module()
    fn = getattr(mod, "normalize_buff_name", None) if mod else None
    if callable(fn):
        try:
            return str(fn(raw) or "").strip()
        except Exception:
            pass
    return raw


def _safe_int_for_condition(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _resolve_buff_count_for_condition(source_obj, buff_name):
    if not isinstance(source_obj, dict):
        return 0
    target_name = _normalize_buff_name_for_condition(buff_name)
    if not target_name:
        return 0

    total = 0
    buffs = source_obj.get("special_buffs", [])
    if not isinstance(buffs, list):
        return 0

    for buff in buffs:
        if not isinstance(buff, dict):
            continue
        if _safe_int_for_condition(buff.get("delay", 0), 0) > 0:
            continue
        row_name = _normalize_buff_name_for_condition(buff.get("name"))
        if row_name != target_name:
            continue
        if buff.get("count") is not None:
            total += max(0, _safe_int_for_condition(buff.get("count"), 0))
            continue
        data = buff.get("data")
        if isinstance(data, dict) and data.get("count") is not None:
            total += max(0, _safe_int_for_condition(data.get("count"), 0))
            continue
        # count未保持バフも「存在1」として扱えるようにする
        total += 1

    return total


def _get_value_for_condition(source_obj, param_name, context=None, actor=None, target=None, source_type=None):
    if source_type == "relation":
        actor_team = _canonical_team((actor or {}).get("type"))
        target_team = _canonical_team((target or {}).get("type"))
        same_team = int(bool(actor_team and target_team and actor_team == target_team))
        target_is_ally = same_team
        target_is_enemy = int(bool(actor_team and target_team and actor_team != target_team))

        if param_name in {"same_team", "target_is_ally"}:
            return same_team if param_name == "same_team" else target_is_ally
        if param_name == "target_is_enemy":
            return target_is_enemy
        return None
    if not source_obj: return None

    normalized_param_name = str(param_name or "").strip()
    if normalized_param_name:
        if normalized_param_name.lower().startswith("buff_count:"):
            buff_name = normalized_param_name.split(":", 1)[1].strip()
            return _resolve_buff_count_for_condition(source_obj, buff_name)
        if normalized_param_name.endswith("_count") and len(normalized_param_name) > len("_count"):
            buff_name = normalized_param_name[:-len("_count")]
            return _resolve_buff_count_for_condition(source_obj, buff_name)

    if normalized_param_name == "tags":
        return source_obj.get("tags", [])

    # 「速度値」はロール結果。旧timeline形式/新battle_state形式/現在値の全てを横断して解決する。
    # 参照不可の場合は 0 ではなく None を返し、低速条件 (<= 4 等) の誤発火を防ぐ。
    if normalized_param_name in {"速度値", "speed_value", "speedvalue", "spd_value"}:
        speed_values = []
        source_id = source_obj.get("id")
        source_slot_id = source_obj.get("slot_id")
        ctx = context if isinstance(context, dict) else {}

        def _append_speed(raw_value):
            if raw_value is None:
                return
            try:
                speed_values.append(int(raw_value))
            except Exception:
                return

        # Prefer shared resolver when available (handles more battle-state variants).
        mod = _utils_module()
        speed_resolver = getattr(mod, "_resolve_actor_round_speed", None) if mod else None
        if callable(speed_resolver):
            try:
                resolved_speed = speed_resolver(source_obj, context=ctx)
                if resolved_speed is not None and int(resolved_speed) > 0:
                    _append_speed(resolved_speed)
            except Exception:
                pass

        for speed_key in ("totalSpeed", "speed", "initiative", "speed_value"):
            if speed_key in source_obj:
                _append_speed(source_obj.get(speed_key))

        timeline = ctx.get("timeline")
        if isinstance(timeline, list):
            for entry in timeline:
                if not isinstance(entry, dict):
                    continue
                entry_char_id = entry.get("char_id") or entry.get("actor_id")
                entry_slot_id = entry.get("id") or entry.get("slot_id")
                if source_id and str(entry_char_id) == str(source_id):
                    _append_speed(entry.get("speed", entry.get("initiative")))
                    continue
                if source_slot_id and str(entry_slot_id) == str(source_slot_id):
                    _append_speed(entry.get("speed", entry.get("initiative")))

        battle_state = ctx.get("battle_state")
        if not isinstance(battle_state, dict):
            room_state = ctx.get("room_state")
            if isinstance(room_state, dict):
                battle_state = room_state.get("battle_state")

        if isinstance(battle_state, dict):
            slots = battle_state.get("slots", {})
            if isinstance(slots, dict):
                for slot_id, slot in slots.items():
                    if not isinstance(slot, dict):
                        continue
                    if source_id and str(slot.get("actor_id")) == str(source_id):
                        _append_speed(slot.get("initiative"))
                        continue
                    if source_slot_id and str(slot_id) == str(source_slot_id):
                        _append_speed(slot.get("initiative"))

        if speed_values:
            return max(speed_values)

        # Fallback: if speed value exists explicitly in status rows, allow it.
        normalized_speed_name = "速度値"
        params = source_obj.get("params", [])
        if isinstance(params, list):
            for row in params:
                if not isinstance(row, dict):
                    continue
                if str(row.get("label", "")).strip() == normalized_speed_name:
                    _append_speed(row.get("value"))
                    break
        states = source_obj.get("states", [])
        if isinstance(states, list):
            for row in states:
                if not isinstance(row, dict):
                    continue
                if str(row.get("name", "")).strip() == normalized_speed_name:
                    _append_speed(row.get("value"))
                    break
        if speed_values:
            return max(speed_values)

        return None

    return get_status_value(source_obj, param_name)

def check_condition(condition_obj, actor, target, target_skill_data=None, actor_skill_data=None, context=None):
    if not condition_obj: return True
    source_str = condition_obj.get("source")
    param_name = condition_obj.get("param")
    op = condition_obj.get("operator")
    check_value = condition_obj.get("value")

    if not source_str or not param_name or not op or check_value is None: return False

    source_obj = None
    if source_str == "self": source_obj = actor
    elif source_str == "target": source_obj = target
    elif source_str == "target_skill": source_obj = target_skill_data
    elif source_str == "skill" or source_str == "actor_skill": source_obj = actor_skill_data
    elif source_str == "relation": source_obj = {}

    # Contextを渡す
    current_value = _get_value_for_condition(
        source_obj,
        param_name,
        context=context,
        actor=actor,
        target=target,
        source_type=source_str,
    )
    if current_value is None: return False

    try:
        if op == "CONTAINS": return check_value in current_value
        current_value = int(current_value)
        check_value = int(check_value)
        if op == "GTE": return current_value >= check_value
        elif op == "LTE": return current_value <= check_value
        elif op == "GT": return current_value > check_value
        elif op == "LT": return current_value < check_value
        elif op == "EQUALS": return current_value == check_value
    except Exception:
        return False
    return False

# ★修正: 汎用ボーナス計算ロジック（内部用）
def _calculate_bonus_from_rules(rules, actor, target, actor_skill_data=None, context=None):
    total = 0
    for rule in rules:
        # 条件チェック
        condition = rule.get('condition')
        if condition:
            if not check_condition(condition, actor, target, actor_skill_data=actor_skill_data, context=context):
                continue

        # 加算値計算
        bonus = 0
        operation = str(rule.get('operation', rule.get('operator', 'FIXED')) or 'FIXED').strip().upper()

        if operation == 'FIXED':
            bonus = int(rule.get('value', 0))

        elif operation in ['MULTIPLY', 'FIXED_IF_EXISTS', 'PER_N_BONUS']:
            src_type = rule.get('source', 'self')
            src_obj = target if src_type == 'target' else actor
            p_name = rule.get('param')
            # ここでも _get_value_for_condition を使うべきだが、
            # ボーナス値の基準にするパラメータ(param)は通常ステータス値(HP, MP, 筋力など)であり、
            # イニシアチブ値(速度)を基準に倍率を掛けることは稀。
            # しかし一貫性を保つため _get_value_for_condition を使うのが良いが、
            # 既存実装は get_status_value を直接呼んでいる。
            # ここでは安全のため既存通り get_status_value にしておく (イニシアチブ値で倍率計算するケースがあれば修正)
            val = get_status_value(src_obj, p_name)

            if operation == 'MULTIPLY':
                bonus = int(val * float(rule.get('value_per_param', 0)))
            elif operation == 'FIXED_IF_EXISTS':
                threshold = int(rule.get('threshold', 1))
                if val >= threshold:
                    bonus = int(rule.get('value', 0))
            elif operation == 'PER_N_BONUS':
                N = int(rule.get('per_N', 1))
                if N > 0:
                    bonus = (val // N) * int(rule.get('value', 0))

        if 'max_bonus' in rule:
            bonus = min(bonus, int(rule['max_bonus']))
        if 'min_bonus' in rule:
            bonus = max(bonus, int(rule['min_bonus']))

        total += bonus
    return total


def _split_power_bonus_rules(rules):
    """
    power_bonus ルールを適用先ごとに分割する。
    apply_to 未指定は base 扱い。
    """
    buckets = {"base": [], "dice": [], "final": []}
    for rule in (rules or []):
        if not isinstance(rule, dict):
            continue
        apply_to = str(rule.get("apply_to", "base") or "base").lower()
        if apply_to == "dice":
            buckets["dice"].append(rule)
        elif apply_to == "final":
            buckets["final"].append(rule)
        else:
            buckets["base"].append(rule)
    return buckets


def _resolve_runtime_buff_effect_data(buff_row):
    """
    Resolve buff effect for runtime calculation.
    Shared resolver:
    1) Catalog/static effect by buff name
    2) Merge/override with buff instance data
    3) Fixed value-driven implementation for Bu-32..Bu-47
    """
    return resolve_runtime_buff_effect(buff_row)


def calculate_buff_power_bonus_parts(actor, target, actor_skill_data, context=None):
    """
    バフ由来の威力補正を適用先ごとに返す。
    Returns: {"base": int, "dice": int, "final": int}
    """
    parts = {"base": 0, "dice": 0, "final": 0}
    if not actor or 'special_buffs' not in actor:
        return parts

    for buff in actor['special_buffs']:
        effect_data = _resolve_runtime_buff_effect_data(buff)
        if not effect_data:
            continue

        if buff.get('delay', 0) > 0:
            continue

        buckets = _split_power_bonus_rules(effect_data.get('power_bonus', []))
        parts["base"] += _calculate_bonus_from_rules(
            buckets["base"], actor, target, actor_skill_data, context=context
        )
        parts["dice"] += _calculate_bonus_from_rules(
            buckets["dice"], actor, target, actor_skill_data, context=context
        )
        parts["final"] += _calculate_bonus_from_rules(
            buckets["final"], actor, target, actor_skill_data, context=context
        )

    return parts


# 後方互換: 既存呼び出しは「定数加算」の総量を期待するため base + final を返す。
def calculate_buff_power_bonus(actor, target, actor_skill_data, context=None):
    parts = calculate_buff_power_bonus_parts(actor, target, actor_skill_data, context=context)
    return int(parts.get("base", 0)) + int(parts.get("final", 0))

def calculate_state_apply_bonus(actor, target, stat_name, context=None):
    total_bonus = 0
    buffs_to_remove = []  # ★削除リスト

    if not actor or 'special_buffs' not in actor:
        return 0, [] # ★

    for buff in actor['special_buffs']:
        buff_name = buff.get('name')
        effect_data = _resolve_runtime_buff_effect_data(buff)
        if not effect_data:
            continue

        # ★追加: ディレイ中のバフは無効
        if buff.get('delay', 0) > 0:
            continue

        state_bonuses = effect_data.get('state_bonus', [])
        matching_rules = [r for r in state_bonuses if r.get('stat') == stat_name]

        # ボーナス計算
        bonus = _calculate_bonus_from_rules(matching_rules, actor, target, None, context=context)

        if bonus > 0:
            total_bonus += bonus
            # ★ルールの中に "consume": True があれば削除リストに追加
            for rule in matching_rules:
                if rule.get('consume'):
                    buffs_to_remove.append(buff_name)
                    break # 1つのバフ定義内で複数ルールがあっても1回削除登録すれば十分

    return total_bonus, buffs_to_remove

def calculate_state_receive_bonus(receiver, source, stat_name, context=None):
    total_bonus = 0
    buffs_to_remove = []

    if not receiver or 'special_buffs' not in receiver:
        return 0, []

    def _resolve_stack_count(buff):
        """受け手側補正のスタック数(count)を正規化して返す。未指定は1。"""
        if not isinstance(buff, dict):
            return 1
        raw_count = buff.get('count')
        if raw_count is None:
            data = buff.get('data')
            if isinstance(data, dict):
                raw_count = data.get('count')
        if raw_count is None:
            return 1
        try:
            return max(0, int(raw_count))
        except Exception:
            return 1

    for buff in receiver['special_buffs']:
        buff_name = buff.get('name')
        effect_data = _resolve_runtime_buff_effect_data(buff)
        if not effect_data:
            continue

        # キャッシュ/参照タイミング差で get_buff_effect(name) が解決できないケース向けフォールバック:
        # buff_id からカタログeffectを引き、受け手側補正ルールを補完する。
        if not isinstance(effect_data, dict):
            effect_data = {}
        if not effect_data.get('state_receive_bonus'):
            try:
                from manager.buff_catalog import get_buff_by_id
                buff_id = str(
                    buff.get('buff_id')
                    or (buff.get('data') or {}).get('buff_id')
                    or ''
                ).strip()
                if buff_id:
                    buff_data = get_buff_by_id(buff_id)
                    if isinstance(buff_data, dict):
                        catalog_effect = buff_data.get('effect')
                        if isinstance(catalog_effect, dict) and catalog_effect.get('state_receive_bonus'):
                            merged = dict(catalog_effect)
                            merged.update(effect_data)
                            effect_data = merged
            except Exception:
                pass

        # ディレイ中のバフは無効
        if buff.get('delay', 0) > 0:
            continue

        receive_rules = effect_data.get('state_receive_bonus', [])
        matching_rules = [r for r in receive_rules if r.get('stat') == stat_name]
        if not matching_rules:
            continue

        stack_count = _resolve_stack_count(buff)
        if stack_count <= 0:
            continue

        bonus_per_stack = _calculate_bonus_from_rules(matching_rules, receiver, source, None, context=context)
        bonus = bonus_per_stack * stack_count

        if bonus > 0:
            total_bonus += bonus
            for rule in matching_rules:
                if rule.get('consume'):
                    buffs_to_remove.append(buff_name)
                    break

    return total_bonus, buffs_to_remove

def execute_custom_effect(effect, actor, target, context=None):
    """
    プラグイン化されたカスタム効果を実行する
    """
    effect_name = effect.get("value")
    registry = _effect_registry()
    handler = registry.get(effect_name)

    if not handler:
        logger.debug(f"Unknown CUSTOM_EFFECT '{effect_name}'")
        return [], []

    try:
        # コンテキストとしてレジストリを渡す（亀裂崩壊などで再帰的に使うため）。
        # 呼び出し側のcontext(キャラ一覧など)も取り込んで、プラグイン側で利用できるようにする。
        plugin_context = {
            "registry": registry
        }
        if isinstance(context, dict):
            plugin_context.update(context)
            plugin_context["registry"] = registry
        return handler.apply(actor, target, effect, plugin_context)
    except Exception as e:
        logger.error(f"Plugin Error ({effect_name}): {e}")
        return [], []

def process_skill_effects(effects_array, timing_to_check, actor, target, target_skill_data=None, context=None, base_damage=0):
    total_bonus_damage = 0
    log_snippets = []
    changes_to_apply = []

    if not actor:
        return 0, [], []
    if not effects_array and timing_to_check != "HIT":
        return 0, [], []

    if timing_to_check == "HIT":
        origin_logs, origin_changes = build_origin_hit_changes(actor, target, context=context)
        if origin_logs:
            log_snippets.extend(origin_logs)
        if origin_changes:
            changes_to_apply.extend(origin_changes)

    stage_state = get_state_from_context(context)
    if timing_to_check in ("PRE_MATCH", "BEFORE_POWER_ROLL", "HIT", "UNOPPOSED"):
        stage_damage_mod = get_stage_damage_dealt_mod(stage_state, actor)
        if stage_damage_mod != 0:
            total_bonus_damage += int(stage_damage_mod)
            log_snippets.append(f"[StageDamage {stage_damage_mod:+} source=stage]")
    if timing_to_check == "HIT" and isinstance(target, dict):
        for st_name, st_value, rule_id in get_stage_state_effects(stage_state, target):
            if st_value == 0:
                continue
            changes_to_apply.append((target, "APPLY_STATE", st_name, st_value))
            rid = f" rule={rule_id}" if rule_id else ""
            log_snippets.append(f"[StageState {st_name}{st_value:+} source=stage{rid}]")

    # Helper for random selection
    import random
    def select_random_targets(actor_obj, effect_def, all_chars):
        # Default settings
        tgt_type = effect_def.get("target_filter", "ENEMY") # ENEMY, ALLY, ALL
        count = int(effect_def.get("target_count", 1))
        include_self = effect_def.get("include_self", False)

        candidates = []
        actor_type = actor_obj.get("type", "ally")

        for c in all_chars:
            # Check placement (must have x, y coordinates to be considered "placed")
            if c.get("x") is None or c.get("y") is None:
                continue

            # Status Check
            if c.get("hp", 0) <= 0: continue
            if c.get("is_escaped"): continue

            # Faction Check
            c_type = c.get("type", "enemy")
            is_ally = (c_type == actor_type)

            if tgt_type == "ENEMY" and is_ally: continue
            if tgt_type == "ALLY" and not is_ally: continue
            # ALL accepts both (except self if excluded)

            # Self Check
            if c.get("id") == actor_obj.get("id") and not include_self:
                continue

            candidates.append(c)

        if not candidates:
            return []

        # Select distinct
        if count >= len(candidates):
            return candidates
        return random.sample(candidates, count)

    import copy # 追加

    # シミュレーション用キャッシュ (ID -> char_obj_copy)
    simulated_chars = {}

    def get_simulated_char(real_char):
        if not real_char: return None
        cid = real_char.get('id')
        if cid not in simulated_chars:
            simulated_chars[cid] = copy.deepcopy(real_char)
        return simulated_chars[cid]

    def _parse_positive_rounds(raw_value):
        try:
            rounds = int(raw_value)
        except (TypeError, ValueError):
            return 0
        return rounds if rounds > 0 else 0

    def _queue_fissure_round_buff(target_obj, sim_target, amount, rounds, source='skill'):
        amount = int(amount or 0)
        rounds = int(rounds or 0)
        if amount <= 0 or rounds <= 0:
            return

        current_val = _stable_get_status_value(sim_target, "亀裂")
        _stable_set_status_value(sim_target, "亀裂", current_val + amount)

        changes_to_apply.append((
            target_obj,
            "APPLY_BUFF",
            f"亀裂_R{rounds}",
            {
                "lasting": rounds,
                "delay": 0,
                "data": {
                    "buff_id": "Bu-Fissure",
                    "source": source,
                    "count": amount,
                    "fissure_count": amount,
                    "original_rounds": rounds
                }
            }
        ))

    def _normalize_buff_name_local(name):
        mod = _utils_module()
        fn = getattr(mod, "normalize_buff_name", None) if mod else None
        if callable(fn):
            try:
                return fn(name)
            except Exception:
                pass
        return str(name or "").strip()

    def _resolve_buff_count_local(buff_row, default=0):
        if not isinstance(buff_row, dict):
            return max(0, int(default or 0))
        try:
            if buff_row.get("count") is not None:
                return max(0, int(buff_row.get("count") or 0))
        except Exception:
            pass
        data = buff_row.get("data")
        if isinstance(data, dict):
            try:
                if data.get("count") is not None:
                    return max(0, int(data.get("count") or 0))
            except Exception:
                pass
        return max(0, int(default or 0))

    def _find_sim_buff(sim_char, buff_name):
        if not isinstance(sim_char, dict):
            return None
        buff_name_n = _normalize_buff_name_local(buff_name)
        buffs = sim_char.get("special_buffs", [])
        if not isinstance(buffs, list):
            return None
        for row in buffs:
            if not isinstance(row, dict):
                continue
            if _normalize_buff_name_local(row.get("name")) == buff_name_n:
                return row
        return None

    def _set_sim_buff_count(sim_char, buff_name, new_count):
        if not isinstance(sim_char, dict):
            return
        buff_name_n = _normalize_buff_name_local(buff_name)
        buffs = sim_char.get("special_buffs", [])
        if not isinstance(buffs, list):
            return
        updated = []
        replaced = False
        for row in buffs:
            if not isinstance(row, dict):
                continue
            if _normalize_buff_name_local(row.get("name")) != buff_name_n:
                updated.append(row)
                continue
            if replaced:
                continue
            if int(new_count or 0) > 0:
                cloned = dict(row)
                cloned["count"] = int(new_count)
                data = dict(cloned.get("data") or {})
                data["count"] = int(new_count)
                cloned["data"] = data
                updated.append(cloned)
                replaced = True
        sim_char["special_buffs"] = updated

    def _queue_remaining_buff(target_obj, sim_bucket, buff_name, remaining):
        changes_to_apply.append((target_obj, "REMOVE_BUFF", buff_name, 0))
        if remaining <= 0:
            return

        preserved_data = {}
        preserved_lasting = -1
        preserved_delay = 0
        explicit_lasting = False
        if isinstance(sim_bucket, dict):
            preserved_data = dict(sim_bucket.get("data") or {})
            try:
                preserved_lasting = int(sim_bucket.get("lasting", -1))
            except (TypeError, ValueError):
                preserved_lasting = -1
            try:
                preserved_delay = int(sim_bucket.get("delay", 0))
            except (TypeError, ValueError):
                preserved_delay = 0
            explicit_lasting = ("lasting" in sim_bucket)
            if sim_bucket.get("buff_id") and "buff_id" not in preserved_data:
                preserved_data["buff_id"] = sim_bucket.get("buff_id")
            if sim_bucket.get("description") and "description" not in preserved_data:
                preserved_data["description"] = sim_bucket.get("description")
            if sim_bucket.get("flavor") and "flavor" not in preserved_data:
                preserved_data["flavor"] = sim_bucket.get("flavor")

        preserved_data["count"] = remaining
        changes_to_apply.append((
            target_obj,
            "APPLY_BUFF",
            buff_name,
            {
                "lasting": preserved_lasting,
                "delay": preserved_delay,
                "count": remaining,
                "data": preserved_data,
                "explicit_lasting": explicit_lasting,
            }
        ))

    for effect in effects_array:
        if effect.get("timing") != timing_to_check: continue

        effect_type = effect.get("type")
        targets_list = []

        # Target Resolution
        t_select = effect.get("target_select") # NORMAL (default), RANDOM

        if t_select == "RANDOM":
            if context and "characters" in context:
                targets_list = select_random_targets(actor, effect, context["characters"])
                if not targets_list:
                    log_snippets.append(f"(対象不在)")
            else:
                 pass
        else:
            # Standard targeting
            t_str = effect.get("target")
            if not t_str: t_str = "target" # Default to target if not specified

            if t_str == "self": targets_list = [actor]
            elif t_str == "target": targets_list = [target] if target else []
            # ★ 追加: 全体対象サポート
            elif t_str == "ALL_ENEMIES" and context and "characters" in context:
                actor_type = actor.get("type", "ally")
                target_type = "enemy" if actor_type == "ally" else "ally"
                targets_list = [c for c in context["characters"] if c.get("type") == target_type and c.get('hp', 0) > 0]
            elif t_str == "ALL_ALLIES" and context and "characters" in context:
                actor_type = actor.get("type", "ally")
                targets_list = [c for c in context["characters"] if c.get("type") == actor_type and c.get('hp', 0) > 0]
            elif t_str == "ALL_OTHER_ALLIES" and context and "characters" in context:
                actor_type = actor.get("type", "ally")
                actor_id = actor.get("id")
                targets_list = [
                    c for c in context["characters"]
                    if c.get("type") == actor_type
                    and c.get('hp', 0) > 0
                    and str(c.get("id")) != str(actor_id)
                ]
            elif t_str == "ALL" and context and "characters" in context:
                 targets_list = [c for c in context["characters"] if c.get('hp', 0) > 0]
            # ★新機能: NEXT_ALLY
            elif t_str == "NEXT_ALLY" and context and "characters" in context and context.get("room"):
                from manager.room_manager import get_room_state
                room_name = context.get("room")
                if room_name:
                    state = get_room_state(room_name)
                    timeline = state.get('timeline', [])

                    if timeline and actor:
                        my_id = actor.get('id')
                        my_type = actor.get('type', 'ally')
                        start_idx = -1
                        try:
                            start_idx = timeline.index(my_id)
                        except ValueError:
                            pass
                        target_id = None
                        search_indices = list(range(start_idx + 1, len(timeline))) + list(range(0, start_idx))
                        for idx in search_indices:
                            tid = timeline[idx]
                            t_char = next((c for c in state['characters'] if c['id'] == tid), None)
                            if t_char and t_char.get('type') == my_type and t_char.get('hp', 0) > 0:
                                target_id = tid
                                break
                        if target_id:
                            found = next((c for c in state['characters'] if c['id'] == target_id), None)
                            if found: targets_list = [found]

        if not targets_list: continue

        for target_obj in targets_list:
            # ★重要: 副作用を防ぐため、判定や内部適用はシミュレーション用オブジェクトで行う
            sim_actor = get_simulated_char(actor)
            sim_target = get_simulated_char(target_obj)

            # 条件判定 (シミュレーション状態に基づく)
            if not check_condition(effect.get("condition"), sim_actor, sim_target, target_skill_data, context=context):
                continue

            if effect_type == "APPLY_FISSURE_BUFFED":
                rounds = _parse_positive_rounds(effect.get("rounds"))
                value = int(effect.get("value", 0))
                if rounds <= 0 or value <= 0:
                    continue

                if not sim_target:
                    continue
                if 'flags' not in sim_target:
                    sim_target['flags'] = {}
                if sim_target['flags'].get('fissure_received_this_round', False):
                    log_snippets.append(f"[亀裂付与失敗: 今ラウンド既に付与済み]")
                    continue

                bonus, buffs_to_remove = calculate_state_apply_bonus(sim_actor, sim_target, "亀裂", context=context)
                final_value = value + max(0, int(bonus or 0))
                if final_value <= 0:
                    continue

                for b_name in buffs_to_remove:
                    remove_buff(sim_actor, b_name)
                    changes_to_apply.append((actor, "REMOVE_BUFF", b_name, 0))
                    log_snippets.append(f"({b_name} 消費)")

                _queue_fissure_round_buff(
                    target_obj=target_obj,
                    sim_target=sim_target,
                    amount=final_value,
                    rounds=rounds,
                    source=effect.get("source", "skill"),
                )
                sim_target['flags']['fissure_received_this_round'] = True
                changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))
                log_snippets.append(f"[亀裂+{final_value} ({rounds}R)]")
                continue

            elif effect_type == "APPLY_STATE":
                # ★後方互換: "state_name"と"name"の両方に対応
                stat_name = effect.get("state_name") or effect.get("name")
                value = int(effect.get("value", 0))
                fissure_rounds = _parse_positive_rounds(effect.get("rounds"))

                # ★亀裂の1ラウンド1回付与制限チェック
                if stat_name == "亀裂" and value > 0 and sim_target:
                    if 'flags' not in sim_target:
                        sim_target['flags'] = {}
                    if sim_target['flags'].get('fissure_received_this_round', False):
                        log_snippets.append(f"[亀裂付与失敗: 今ラウンド既に付与済み]")
                        continue  # この効果をスキップし、次の効果へ

                # 正値付与時のみ、付与側/受け手側の状態付与ボーナスを適用
                if value > 0:
                    if sim_actor:
                        source_bonus, source_buffs_to_remove = calculate_state_apply_bonus(
                            sim_actor, sim_target, stat_name, context=context
                        )
                        if source_bonus > 0:
                            value += source_bonus
                        for b_name in source_buffs_to_remove:
                            remove_buff(sim_actor, b_name)
                            changes_to_apply.append((actor, "REMOVE_BUFF", b_name, 0))
                            log_snippets.append(f"({b_name} 消費)")

                    if sim_target:
                        receive_bonus, receive_buffs_to_remove = calculate_state_receive_bonus(
                            sim_target, sim_actor, stat_name, context=context
                        )
                        if receive_bonus > 0:
                            value += receive_bonus
                        for b_name in receive_buffs_to_remove:
                            remove_buff(sim_target, b_name)
                            changes_to_apply.append((target_obj, "REMOVE_BUFF", b_name, 0))
                            log_snippets.append(f"({b_name} 消費)")

                if stat_name and value != 0:
                    if stat_name == "亀裂" and value > 0 and fissure_rounds > 0:
                        _queue_fissure_round_buff(
                            target_obj=target_obj,
                            sim_target=sim_target,
                            amount=value,
                            rounds=fissure_rounds,
                            source=effect.get("source", "skill"),
                        )
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True
                        changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))
                        log_snippets.append(f"[亀裂+{value} ({fissure_rounds}R)]")
                        continue

                    # ★即座に状態を更新（シミュレーション用オブジェクトに対してのみ）
                    current_val = _stable_get_status_value(sim_target, stat_name)
                    _stable_set_status_value(sim_target, stat_name, current_val + value)

                    # 変更ログとして記録（後続の処理で実体に適用される）
                    changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, value)) # 実体に対する変更予約

                    # ★亀裂の場合はフラグを立てる（付与成功時）
                    if stat_name == "亀裂" and value > 0:
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True
                        changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))


            elif effect_type == "APPLY_STATE_PER_N":
                source_type = effect.get("source", "self")
                source_obj = sim_actor if source_type == "self" else sim_target # シミュレーションを使用
                source_param = effect.get("source_param")
                fissure_rounds = _parse_positive_rounds(effect.get("rounds"))

                if not source_obj or not source_param:
                    continue

                # 基準パラメータの値を取得
                source_param_value = _stable_get_status_value(source_obj, source_param)

                # N毎に計算
                per_N = int(effect.get("per_N", 1))
                value_per = int(effect.get("value", 1))
                calculated_value = (source_param_value // per_N) * value_per if per_N > 0 else 0

                # 最大値制限
                if "max_value" in effect:
                    calculated_value = min(calculated_value, int(effect["max_value"]))

                # 付与実行
                stat_name = effect.get("state_name")
                if stat_name and calculated_value > 0:
                    # 亀裂の1ラウンド1回付与制限チェック
                    if stat_name == "亀裂" and sim_target:
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        if sim_target['flags'].get('fissure_received_this_round', False):
                            log_snippets.append(f"[亀裂付与失敗: 今ラウンド既に付与済み]")
                            continue

                    # 正値付与時のみ、付与側/受け手側の状態付与ボーナスを適用
                    if sim_actor:
                        source_bonus, source_buffs_to_remove = calculate_state_apply_bonus(
                            sim_actor, sim_target, stat_name, context=context
                        )
                        if source_bonus > 0:
                            calculated_value += source_bonus
                        for b_name in source_buffs_to_remove:
                            remove_buff(sim_actor, b_name)
                            changes_to_apply.append((actor, "REMOVE_BUFF", b_name, 0))
                            log_snippets.append(f"({b_name} 消費)")

                    if sim_target:
                        receive_bonus, receive_buffs_to_remove = calculate_state_receive_bonus(
                            sim_target, sim_actor, stat_name, context=context
                        )
                        if receive_bonus > 0:
                            calculated_value += receive_bonus
                        for b_name in receive_buffs_to_remove:
                            remove_buff(sim_target, b_name)
                            changes_to_apply.append((target_obj, "REMOVE_BUFF", b_name, 0))
                            log_snippets.append(f"({b_name} 消費)")

                    # rounds 指定時の新方式（時限亀裂）
                    if stat_name == "亀裂" and fissure_rounds > 0:
                        _queue_fissure_round_buff(
                            target_obj=target_obj,
                            sim_target=sim_target,
                            amount=calculated_value,
                            rounds=fissure_rounds,
                            source=effect.get("source", "skill"),
                        )
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True
                        changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))
                        log_snippets.append(f"[亀裂+{calculated_value} ({source_param}{source_param_value}から/{fissure_rounds}R)]")
                        continue

                    # ★即座に状態を更新 (シミュレーション)
                    current_val = _stable_get_status_value(sim_target, stat_name)
                    _stable_set_status_value(sim_target, stat_name, current_val + calculated_value)

                    # 変更ログとして記録 (実体)
                    changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, calculated_value))
                    log_snippets.append(f"[{stat_name}+{calculated_value} ({source_param}{source_param_value}から)]")

                    # 亀裂の場合はフラグを立てる
                    if stat_name == "亀裂":
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True
                        changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))


            elif effect_type == "MULTIPLY_STATE":
                stat_name = effect.get("state_name")
                multiplier = float(effect.get("value", 1.0))

                if stat_name and sim_target:
                    current_val = _stable_get_status_value(sim_target, stat_name)
                    new_val = int(current_val * multiplier + 0.5)
                    diff = new_val - current_val

                    if diff != 0:
                        # ★即座に状態を更新 (シミュレーション)
                        _stable_set_status_value(sim_target, stat_name, new_val)

                        # 変更ログとして記録 (実体)
                        changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, diff))
                        log_snippets.append(f"[{stat_name} x{multiplier} ({current_val}→{new_val})]")


            elif effect_type == "APPLY_BUFF":
                buff_name = effect.get("buff_name")
                buff_id = effect.get("buff_id")

                # ★修正: buff_idが指定されている場合、buff_catalogから名前を取得
                if not buff_name and buff_id:
                    from manager.buff_catalog import get_buff_by_id
                    buff_data = get_buff_by_id(buff_id)
                    if buff_data:
                        buff_name = buff_data.get("name")
                        logger.debug(f"Resolved buff_id '{buff_id}' to buff_name '{buff_name}'")
                    else:
                        logger.warning(f"buff_id '{buff_id}' not found in catalog")

                if buff_name:
                    # ★修正: buff_idも一緒にdataに含める（プラグイン判定用）
                    # さらに description, flavor もカタログから引き継ぐ
                    effect_data = effect.get("data")
                    if effect_data is None:
                        effect_data = {}
                    else:
                        # 呼び出し元の副作用を防ぐためコピー
                        effect_data = effect_data.copy()

                    if buff_id:
                        effect_data["buff_id"] = buff_id

                        # カタログから詳細情報を取得してマージ
                        if 'buff_data' in locals() and buff_data:
                            if "description" not in effect_data:
                                effect_data["description"] = buff_data.get("description", "")
                            if "flavor" not in effect_data:
                                effect_data["flavor"] = buff_data.get("flavor", "")

                            # ★追加: stat_mod の継承 (Phase 10 後半)
                            # カタログ定義の effect: { type: "stat_mod", stat: "基礎威力", value: 1 }
                            # を、システムが解釈できる stat_mods: { "基礎威力": 1 } に変換する
                            catalog_effect = buff_data.get("effect", {})
                            if catalog_effect.get("type") == "stat_mod":
                                stat_name = catalog_effect.get("stat")
                                mod_value = catalog_effect.get("value")

                                if stat_name and mod_value is not None:
                                    if "stat_mods" not in effect_data:
                                        effect_data["stat_mods"] = {}
                                    effect_data["stat_mods"][stat_name] = mod_value
                                    # print(f"[APPLY_BUFF] Converted stat_mod for {buff_name}: {stat_name}={mod_value}")

                    # ★追加: 動的パターンや静的定義から得られる効果データをマージ
                    # (buff_idがなく、buff_nameのみの場合や、動的生成されたプロパティを取り込む)
                    from manager.buff_catalog import get_buff_effect
                    catalog_effect_data = get_buff_effect(buff_name)
                    if isinstance(catalog_effect_data, dict):
                        # 既存のeffect_dataにマージ
                        for k, v in catalog_effect_data.items():
                            if k not in effect_data:
                                effect_data[k] = v
                            elif k == "stat_mods" and isinstance(v, dict):
                                # stat_modsはマージ
                                if "stat_mods" not in effect_data:
                                    effect_data["stat_mods"] = {}
                                for sk, sv in v.items():
                                    if sk not in effect_data["stat_mods"]:
                                        effect_data["stat_mods"][sk] = sv

                    # ★追加: flavorテキストの継承
                    if "flavor" in effect:
                        effect_data["flavor"] = effect["flavor"]

                    default_lasting = -1 if _normalize_buff_name_local(buff_name) in {"凝魔", "蓄力"} else 1
                    raw_lasting = effect.get("lasting", default_lasting)
                    try:
                        parsed_lasting = int(raw_lasting)
                    except (TypeError, ValueError):
                        parsed_lasting = default_lasting
                    try:
                        parsed_delay = int(effect.get("delay", 0))
                    except (TypeError, ValueError):
                        parsed_delay = 0
                    buff_payload = {
                        "lasting": parsed_lasting,
                        "delay": parsed_delay,
                        "data": effect_data,
                        "explicit_lasting": ("lasting" in effect),
                    }
                    if "count" in effect:
                        try:
                            parsed_count = int(effect.get("count"))
                        except (TypeError, ValueError):
                            parsed_count = 0
                        if parsed_count > 0:
                            buff_payload["count"] = parsed_count
                            if isinstance(effect_data, dict) and "count" not in effect_data:
                                effect_data["count"] = parsed_count
                    changes_to_apply.append((target_obj, "APPLY_BUFF", buff_name, buff_payload))
                    log_snippets.append(f"[{buff_name} 付与]")
            elif effect_type == "CONSUME_BUFF_COUNT_FOR_GAIN":
                buff_name = effect.get("buff_name")
                if not buff_name:
                    continue
                try:
                    consume_required = int(effect.get("consume_required", 0))
                except (TypeError, ValueError):
                    consume_required = 0
                if consume_required <= 0:
                    continue

                sim_bucket = _find_sim_buff(sim_target, buff_name)
                current_count = _resolve_buff_count_local(sim_bucket, default=0)
                if current_count < consume_required:
                    log_snippets.append(f"[{buff_name}不足 {current_count}/{consume_required}]")
                    continue

                remaining = current_count - consume_required
                _set_sim_buff_count(sim_target, buff_name, remaining)
                _queue_remaining_buff(target_obj, sim_bucket, buff_name, remaining)

                gains = effect.get("gains", [])
                if isinstance(gains, dict):
                    gains = [gains]
                gain_count = 0
                if isinstance(gains, list):
                    for gain in gains:
                        if not isinstance(gain, dict):
                            continue
                        gain_type = str(gain.get("type", "")).strip().upper()
                        if gain_type in {"FP", "MP", "HP"}:
                            try:
                                gain_value = int(gain.get("value", 0))
                            except (TypeError, ValueError):
                                gain_value = 0
                            if gain_value == 0:
                                continue
                            current_val = _stable_get_status_value(sim_target, gain_type)
                            _stable_set_status_value(sim_target, gain_type, current_val + gain_value)
                            changes_to_apply.append((target_obj, "APPLY_STATE", gain_type, gain_value))
                            gain_count += 1
                        elif gain_type in {"BUFF", "APPLY_BUFF"}:
                            gain_buff_name = gain.get("buff_name")
                            if not gain_buff_name:
                                continue
                            try:
                                gain_lasting = int(gain.get("lasting", 1))
                            except (TypeError, ValueError):
                                gain_lasting = 1
                            try:
                                gain_delay = int(gain.get("delay", 0))
                            except (TypeError, ValueError):
                                gain_delay = 0
                            gain_data = gain.get("data")
                            if gain_data is None:
                                gain_data = {}
                            elif isinstance(gain_data, dict):
                                gain_data = dict(gain_data)
                            else:
                                continue
                            gain_payload = {
                                "lasting": gain_lasting,
                                "delay": gain_delay,
                                "data": gain_data,
                                "explicit_lasting": ("lasting" in gain),
                            }
                            if "count" in gain:
                                try:
                                    gain_payload["count"] = int(gain.get("count"))
                                except (TypeError, ValueError):
                                    pass
                            changes_to_apply.append((target_obj, "APPLY_BUFF", gain_buff_name, gain_payload))
                            gain_count += 1

                log_snippets.append(f"[{buff_name} {consume_required}消費]")
                if gain_count > 0:
                    log_snippets.append(f"[追加効果 {gain_count}件]")
            elif effect_type == "CONSUME_BUFF_COUNT_FOR_POWER":
                buff_name = effect.get("buff_name")
                if not buff_name:
                    continue

                try:
                    consume_max = int(effect.get("consume_max", 0))
                except (TypeError, ValueError):
                    consume_max = 0
                if consume_max <= 0:
                    continue

                try:
                    value_per_stack = int(effect.get("value_per_stack", 1))
                except (TypeError, ValueError):
                    value_per_stack = 1
                if value_per_stack == 0:
                    continue

                try:
                    min_consume = int(effect.get("min_consume", 1))
                except (TypeError, ValueError):
                    min_consume = 1
                if min_consume < 1:
                    min_consume = 1

                apply_to = str(effect.get("apply_to", "final") or "final").strip().lower()
                if apply_to not in {"base", "final"}:
                    apply_to = "final"

                sim_bucket = _find_sim_buff(sim_target, buff_name)
                current_count = _resolve_buff_count_local(sim_bucket, default=0)
                consume_amount = min(current_count, consume_max)
                if consume_amount < min_consume:
                    log_snippets.append(f"[{buff_name}不足 {current_count}/{min_consume}]")
                    continue

                remaining = current_count - consume_amount
                _set_sim_buff_count(sim_target, buff_name, remaining)
                _queue_remaining_buff(target_obj, sim_bucket, buff_name, remaining)

                power_delta = consume_amount * value_per_stack
                if power_delta != 0:
                    change_type = "MODIFY_BASE_POWER" if apply_to == "base" else "MODIFY_FINAL_POWER"
                    changes_to_apply.append((target_obj, change_type, None, power_delta))
                    bonus_label = "基礎威力" if apply_to == "base" else "最終威力"
                    log_snippets.append(f"[{buff_name} {consume_amount}消費 -> {bonus_label}{power_delta:+}]")
                else:
                    log_snippets.append(f"[{buff_name} {consume_amount}消費]")
            elif effect_type == "GRANT_SKILL":
                grant_skill_id = str(effect.get("skill_id", effect.get("grant_skill_id", "")) or "").strip()
                if not grant_skill_id:
                    continue
                grant_payload = {
                    "skill_id": grant_skill_id,
                    "grant_mode": effect.get("grant_mode", "permanent"),
                    "duration": effect.get("duration", effect.get("rounds")),
                    "uses": effect.get("uses", effect.get("count")),
                    "custom_name": effect.get("custom_name"),
                    "overwrite": effect.get("overwrite", True),
                    "source_skill_id": effect.get("source_skill_id"),
                }
                changes_to_apply.append((target_obj, "GRANT_SKILL", grant_skill_id, grant_payload))
                log_snippets.append(f"[スキル付与:{grant_skill_id}]")
            elif effect_type == "REMOVE_BUFF":
                buff_name = effect.get("buff_name")
                if buff_name:
                    changes_to_apply.append((target_obj, "REMOVE_BUFF", buff_name, 0))
                    log_snippets.append(f"[{buff_name} 解除]")
            elif effect_type == "DAMAGE_BONUS":
                damage = int(effect.get("value", 0))
                if damage > 0:
                    total_bonus_damage += damage
                    log_snippets.append(f"+ [追加ダメージ {damage}]")
            elif effect_type == "MODIFY_ROLL":
                mod_value = int(effect.get("value", 0))
                if mod_value != 0:
                    total_bonus_damage += mod_value
                    log_snippets.append(f"[ロール修正 {mod_value:+,}]")
            elif effect_type == "USE_SKILL_AGAIN":
                # Resolve-layer feature: request reusing the same skill against the same slot target.
                max_reuses = effect.get("max_reuses", effect.get("max_reuse_count", effect.get("value", 1)))
                try:
                    max_reuses = int(max_reuses)
                except (TypeError, ValueError):
                    max_reuses = 1
                max_reuses = max(1, max_reuses)

                consume_cost = bool(effect.get("consume_cost", False))
                raw_reuse_cost = effect.get("reuse_cost", effect.get("reuse_costs", []))
                if isinstance(raw_reuse_cost, dict):
                    raw_reuse_cost = [raw_reuse_cost]
                reuse_cost = []
                if isinstance(raw_reuse_cost, list):
                    for entry in raw_reuse_cost:
                        if not isinstance(entry, dict):
                            continue
                        c_type = str(entry.get("type", "")).strip()
                        if not c_type:
                            continue
                        try:
                            c_val = int(entry.get("value", 0))
                        except (TypeError, ValueError):
                            c_val = 0
                        if c_val <= 0:
                            continue
                        reuse_cost.append({"type": c_type, "value": c_val})
                request_payload = {
                    "max_reuses": max_reuses,
                    "consume_cost": consume_cost,
                }
                if reuse_cost:
                    request_payload["reuse_cost"] = reuse_cost
                changes_to_apply.append((target_obj, "USE_SKILL_AGAIN", "None", request_payload))
                log_snippets.append(f"[同スキル再使用 x{max_reuses}]")
            elif effect_type == "CUSTOM_EFFECT":
                # target="self" の場合は自分を対象にする。
                # 重要: CUSTOM_EFFECT もシミュレーション状態を参照させる。
                # これにより、同一 effects 配列内で先行した APPLY_STATE の結果を正しく反映できる。
                custom_target_sim = sim_actor if effect.get("target") == "self" else sim_target
                custom_changes, custom_logs = execute_custom_effect(effect, sim_actor, custom_target_sim, context=context)

                # 実適用キューには実体参照を積むため、sim参照を actor/target_obj に戻す。
                remapped_changes = []
                for c, t, n, v in custom_changes:
                    mapped_char = c
                    if c is sim_actor:
                        mapped_char = actor
                    elif c is sim_target:
                        mapped_char = target_obj
                    remapped_changes.append((mapped_char, t, n, v))

                changes_to_apply.extend(remapped_changes)
                log_snippets.extend(custom_logs)
            elif effect_type == "FORCE_UNOPPOSED":
                changes_to_apply.append((target_obj, "FORCE_UNOPPOSED", "None", 0))
            elif effect_type == "MODIFY_BASE_POWER":
                mod_value = int(effect.get("value", 0))
                if mod_value != 0:
                    changes_to_apply.append((target_obj, "MODIFY_BASE_POWER", None, mod_value))
                    log_snippets.append(f"[基礎威力 {mod_value:+}]")
            elif effect_type == "MODIFY_FINAL_POWER":
                mod_value = int(effect.get("value", 0))
                if mod_value != 0:
                    changes_to_apply.append((target_obj, "MODIFY_FINAL_POWER", None, mod_value))
                    log_snippets.append(f"[最終威力 {mod_value:+}]")
            elif effect_type == "DRAIN_HP":
                 # ★追加: ダメージ吸収 (base_damageに基づく)
                 if base_damage > 0:
                     rate = float(effect.get("value", 0))

                     # ★ 追加: 対象(攻撃相手)のHPを上限にする
                     calc_base = base_damage
                     if target: # 攻撃対象が存在する場合
                         target_current_hp = _stable_get_status_value(target, 'HP')
                         if target_current_hp < calc_base:
                             calc_base = target_current_hp

                     heal_val = int(calc_base * rate)
                     if heal_val > 0:
                         # 即座に回復 (シミュレーション)
                         current_hp = _stable_get_status_value(sim_actor, 'HP')
                         _stable_set_status_value(sim_actor, 'HP', current_hp + heal_val)

                         # 変更予約 (実体)
                         changes_to_apply.append((actor, "APPLY_STATE", "HP", heal_val))
                         log_snippets.append(f"[吸収 {heal_val}]")
            elif effect_type == "SUMMON_CHARACTER":
                summon_template_id = (
                    effect.get("summon_template_id")
                    or effect.get("template_id")
                    or effect.get("summon_id")
                )
                if not summon_template_id:
                    continue
                summon_payload = {
                    "summon_template_id": summon_template_id,
                }
                duration_mode_raw = effect.get("summon_duration_mode", effect.get("duration_mode"))
                if duration_mode_raw not in (None, ""):
                    summon_payload["summon_duration_mode"] = duration_mode_raw
                duration_raw = effect.get("summon_duration", effect.get("duration"))
                if duration_raw not in (None, ""):
                    summon_payload["summon_duration"] = duration_raw
                summon_team_raw = effect.get("summon_type", effect.get("summon_team"))
                if summon_team_raw not in (None, ""):
                    summon_payload["type"] = summon_team_raw
                for key in [
                    "name",
                    "base_name",
                    "x",
                    "y",
                    "offset_x",
                    "offset_y",
                    "commands",
                    "initial_skill_ids",
                    "custom_skill_names",
                    "SPassive",
                    "special_buffs",
                    "radiance_skills",
                    "params",
                    "states",
                    "hp",
                    "maxHp",
                    "mp",
                    "maxMp",
                ]:
                    if key in effect:
                        summon_payload[key] = copy.deepcopy(effect.get(key))

                # target を別に取る定義では、座標が未指定なら target 座標をスポーン地点に使う。
                if (
                    isinstance(target_obj, dict)
                    and target_obj.get("id") != actor.get("id")
                    and "x" not in summon_payload
                    and "y" not in summon_payload
                ):
                    summon_payload["x"] = target_obj.get("x")
                    summon_payload["y"] = target_obj.get("y")

                changes_to_apply.append((actor, "SUMMON_CHARACTER", str(summon_template_id), summon_payload))
                log_snippets.append(f"[召喚:{summon_template_id}]")


    return total_bonus_damage, log_snippets, changes_to_apply

def calculate_power_bonus(actor, target, power_bonus_data, context=None):
    # (この関数は変更なし、ロジックそのまま)
    def _get_bonus(rule, s, t):
        if not rule: return 0
        src = s if rule.get('source') != 'target' else t
        if not src: return 0
        p_name = rule.get('param')
        val = _get_value_for_condition(src, p_name, context=context) # ★修正: ここも context対応
        bonus = 0
        op = str(rule.get('operation', rule.get('operator', '')) or '').strip().upper()
        if op == 'MULTIPLY':
            bonus = int(val * float(rule.get('value_per_param', 0)))
        elif op == 'FIXED_IF_EXISTS':
            if val >= 1: bonus = int(rule.get('value', 0))
        elif op == 'PER_N_BONUS':
            N = int(rule.get('per_N', 1))
            if N > 0: bonus = (val // N) * int(rule.get('value', 0))
        if 'max_bonus' in rule:
            bonus = min(bonus, int(rule['max_bonus']))
        return bonus

    total = 0
    if isinstance(power_bonus_data, list):
        for rule in power_bonus_data: total += _get_bonus(rule, actor, target)
    elif isinstance(power_bonus_data, dict):
        rule = power_bonus_data.get("power_bonus", power_bonus_data)
        total = _get_bonus(rule, actor, target)
    return total

def _resolve_power_stat_choice(skill_data, rule_data, actor_char):
    def _to_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    candidates = []
    if isinstance(skill_data, dict) and isinstance(skill_data.get("power_stat_choice"), dict):
        candidates.append(skill_data.get("power_stat_choice"))
    if isinstance(rule_data, dict) and isinstance(rule_data.get("power_stat_choice"), dict):
        candidates.append(rule_data.get("power_stat_choice"))
    choice = next((c for c in candidates if isinstance(c, dict)), None)
    if not isinstance(choice, dict):
        return None

    mode = str(choice.get("mode", "max") or "max").strip().lower()
    params = choice.get("params", [])
    if not isinstance(params, list) or not params:
        return None
    tie_breaker = str(choice.get("tie_breaker", "") or "").strip()
    apply_as = str(choice.get("apply_as", "final_power") or "final_power").strip().lower()

    rows = []
    for idx, param_name in enumerate(params):
        label = str(param_name or "").strip()
        if not label:
            continue
        rows.append({
            "index": idx,
            "param": label,
            "value": _to_int(get_status_value(actor_char, label), 0),
        })
    if not rows:
        return None

    if mode == "max":
        selected = max(
            rows,
            key=lambda row: (
                row["value"],
                1 if tie_breaker and row["param"] == tie_breaker else 0,
                -row["index"],
            )
        )
    else:
        selected = rows[0]

    return {
        "mode": mode,
        "params": [row["param"] for row in rows],
        "tie_breaker": tie_breaker,
        "apply_as": apply_as,
        "selected_param": selected["param"],
        "selected_value": int(selected["value"]),
    }


def calculate_skill_preview(
    actor_char,
    target_char,
    skill_data,
    rule_data=None,
    custom_skill_name=None,
    senritsu_max_apply=0,
    external_base_power_mod=0,
    external_final_power_mod=0,
    context=None
):
    """
    スキルの威力、コマンド、補正情報のプレビューデータを計算する。
    """
    def _to_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    actor_char = actor_char if isinstance(actor_char, dict) else {}
    target_char = target_char if isinstance(target_char, dict) else {}
    skill_data = skill_data if isinstance(skill_data, dict) else {}

    origin_modifiers = compute_origin_skill_modifiers(actor_char, target_char, skill_data, context=context)
    origin_base_power_mod = _to_int(origin_modifiers.get('base_power_bonus', 0))
    origin_final_power_mod = _to_int(origin_modifiers.get('final_power_bonus', 0))
    origin_dice_power_mod = _to_int(origin_modifiers.get('dice_power_bonus', 0))

    raw_base_power = _to_int(skill_data.get('基礎威力', 0))
    base_power_buff_mod = _to_int(get_buff_stat_mod(actor_char, '基礎威力'))
    temp_base_power_mod = _to_int(actor_char.get('_base_power_bonus', 0))
    temp_final_power_mod = _to_int(actor_char.get('_final_power_bonus', 0))

    final_base_power = (
        raw_base_power
        + base_power_buff_mod
        + _to_int(external_base_power_mod)
        + temp_base_power_mod
        + origin_base_power_mod
    )

    skill_details = {
        'base_power': raw_base_power,
        'base_power_buff_mod': base_power_buff_mod,
        'temp_base_power_mod': temp_base_power_mod,
        'external_mod': _to_int(external_base_power_mod),
        'origin_base_power_mod': origin_base_power_mod,
        'origin_final_power_mod': origin_final_power_mod,
        'origin_dice_power_mod': origin_dice_power_mod,
        'final_base_power': final_base_power,
        'final_power_mod': _to_int(external_final_power_mod) + temp_final_power_mod + origin_final_power_mod,
        '分類': skill_data.get('分類', skill_data.get('タイミング', '')),
        '距離': skill_data.get('距離', skill_data.get('射程', '')),
        '属性': skill_data.get('属性', ''),
        '使用時効果': skill_data.get('使用時効果', skill_data.get('コスト', '')),
        '発動時効果': skill_data.get('発動時効果', skill_data.get('効果', '')),
        '特記': skill_data.get('特記', ''),
    }

    # ルールデータの自動パース
    if not rule_data and skill_data:
        try:
            rule_json_str = skill_data.get('特記処理', '{}')
            rule_data = json.loads(rule_json_str) if rule_json_str else {}
        except Exception:
            rule_data = {}

    bonus_power = 0                 # 従来の威力補正(base/default)
    final_power_bonus = _to_int(external_final_power_mod) + temp_final_power_mod + origin_final_power_mod
    dice_bonus_power = origin_dice_power_mod

    rule_base_bonus = 0
    rule_final_bonus = 0
    rule_dice_bonus = 0

    if rule_data:
        rules = rule_data.get('power_bonus', [])
        buckets = _split_power_bonus_rules(rules)

        rule_base_bonus = _calculate_bonus_from_rules(
            buckets["base"], actor_char, target_char, actor_skill_data=skill_data, context=context
        )
        rule_dice_bonus = _calculate_bonus_from_rules(
            buckets["dice"], actor_char, target_char, actor_skill_data=skill_data, context=context
        )
        rule_final_bonus = _calculate_bonus_from_rules(
            buckets["final"], actor_char, target_char, actor_skill_data=skill_data, context=context
        )

        bonus_power += rule_base_bonus
        dice_bonus_power += rule_dice_bonus
        final_power_bonus += rule_final_bonus

        if senritsu_max_apply == 0:
            senritsu_max_apply = rule_data.get('senritsu_max', 0)

    power_stat_choice = _resolve_power_stat_choice(skill_data, rule_data, actor_char)
    selected_power_value = 0
    selected_power_param = None
    if isinstance(power_stat_choice, dict):
        selected_power_value = _to_int(power_stat_choice.get("selected_value", 0), 0)
        selected_power_param = str(power_stat_choice.get("selected_param", "") or "").strip() or None

    # 物理/魔法スキルなら戦慄上限をデフォルト適用
    if senritsu_max_apply == 0:
        category = skill_data.get('分類', '')
        if category and ('物理' in category or '魔法' in category):
            senritsu_max_apply = 3

    # バフ由来補正（apply_to=base/dice/final を分離）
    buff_bonus_parts = calculate_buff_power_bonus_parts(
        actor_char, target_char, skill_data, context=context
    )
    bonus_power += _to_int(buff_bonus_parts.get("base", 0))
    dice_bonus_power += _to_int(buff_bonus_parts.get("dice", 0))
    final_power_bonus += _to_int(buff_bonus_parts.get("final", 0))

    # 固有恩恵
    wadatsumi_bonus = 0
    valvile_correction = 0
    try:
        if get_effective_origin_id(actor_char) == 9 and skill_data.get('属性') == '斬撃':
            wadatsumi_bonus = 1
    except Exception:
        wadatsumi_bonus = 0
    try:
        if target_char and get_effective_origin_id(target_char) == 13:
            valvile_correction = -1
    except Exception:
        valvile_correction = 0

    final_power_bonus += wadatsumi_bonus
    final_power_bonus += valvile_correction

    total_flat_bonus = bonus_power + final_power_bonus
    if selected_power_value and isinstance(power_stat_choice, dict):
        if power_stat_choice.get("apply_as") == "final_power":
            total_flat_bonus += selected_power_value
    skill_details['senritsu_max_apply'] = senritsu_max_apply
    skill_details['additional_power'] = total_flat_bonus
    skill_details['base_power_mod'] = base_power_buff_mod + _to_int(external_base_power_mod) + temp_base_power_mod + origin_base_power_mod
    skill_details['final_power_total_mod'] = final_power_bonus

    # ダイス部分の解析
    palette = skill_data.get('チャットパレット', '')
    cmd_part = re.sub(r'【.*?】', '', palette).strip()

    match_base = re.match(r'^(\d+)(.*)$', cmd_part)
    if match_base:
        dice_part = match_base.group(2).strip()
        if not dice_part:
            dice_part = skill_data.get('ダイス威力', '')
    else:
        if '+' in cmd_part:
            dice_part = cmd_part.split('+', 1)[1]
        else:
            dice_part = skill_data.get('ダイス威力', '2d6')

    resolved_dice = resolve_placeholders(dice_part, actor_char)

    # 補正表示（UI向け）
    correction_details = []
    total_base_mod = base_power_buff_mod + _to_int(external_base_power_mod) + temp_base_power_mod + origin_base_power_mod
    if total_base_mod != 0:
        correction_details.append({'source': '基礎威力', 'value': total_base_mod})

    phys_mod = _to_int(get_status_value(actor_char, '物理補正'))
    mag_mod = _to_int(get_status_value(actor_char, '魔法補正'))
    dice_pow_mod = _to_int(get_status_value(actor_char, 'ダイス威力'))

    delta_phys = 0
    delta_mag = 0
    delta_dice_pow = 0

    if '{物理補正}' in dice_part and phys_mod != 0:
        base_phys = _to_int((actor_char.get('initial_data') or {}).get('物理補正', 0))
        delta_phys = phys_mod - base_phys
        if delta_phys != 0:
            correction_details.append({'source': '物理補正', 'value': delta_phys})

    if '{魔法補正}' in dice_part and mag_mod != 0:
        base_mag = _to_int((actor_char.get('initial_data') or {}).get('魔法補正', 0))
        delta_mag = mag_mod - base_mag
        if delta_mag != 0:
            correction_details.append({'source': '魔法補正', 'value': delta_mag})

    if '{ダイス威力}' in dice_part and dice_pow_mod != 0:
        base_dice_pow = _to_int((actor_char.get('initial_data') or {}).get('ダイス威力', 0))
        delta_dice_pow = dice_pow_mod - base_dice_pow
        if delta_dice_pow != 0:
            correction_details.append({'source': 'ダイス威力', 'value': delta_dice_pow})

    if bonus_power != 0:
        correction_details.append({'source': '威力補正', 'value': bonus_power})

    final_power_display = final_power_bonus - valvile_correction
    if final_power_display != 0:
        correction_details.append({'source': '最終威力補正', 'value': final_power_display})

    if valvile_correction != 0:
        correction_details.append({'source': 'ヴァルヴァイレ恩恵', 'value': valvile_correction})

    processed_dice = resolved_dice
    if dice_bonus_power != 0:
        def modify_dice_faces(m):
            sign = m.group(1) or ''
            num = m.group(2)
            faces = int(m.group(3))
            new_faces = max(1, faces + dice_bonus_power)
            return f"{sign}{num}d{new_faces}"

        processed_dice = re.sub(r'([+-]?)(\d+)d(\d+)', modify_dice_faces, processed_dice, count=1)
        correction_details.append({'source': 'ダイス威力', 'value': dice_bonus_power})

    senritsu_dice_reduction = 0
    if senritsu_max_apply > 0:
        current_senritsu = _to_int(get_status_value(actor_char, '戦慄'))
        apply_val = min(current_senritsu, senritsu_max_apply) if current_senritsu > 0 else 0

        dice_m = re.search(r'([+-]?)(\d+)d(\d+)', skill_data.get('ダイス威力', ''))
        if dice_m and apply_val > 0:
            orig_faces = int(dice_m.group(3))
            if orig_faces > 1:
                max_red = orig_faces - 1
                senritsu_dice_reduction = min(apply_val, max_red)

                def reduce_dice_faces(m):
                    sign = m.group(1) or ''
                    num = m.group(2)
                    faces = int(m.group(3))
                    new_faces = max(1, faces - senritsu_dice_reduction)
                    return f"{sign}{num}d{new_faces}"

                processed_dice = re.sub(r'([+-]?)(\d+)d(\d+)', reduce_dice_faces, processed_dice, count=1)
                skill_details['senritsu_dice_reduction'] = senritsu_dice_reduction

    final_dice_part = processed_dice
    if total_flat_bonus != 0:
        if str(processed_dice).strip() in ['', '0']:
            final_dice_part = f"{total_flat_bonus}"
        else:
            final_dice_part += f"{'+' if total_flat_bonus > 0 else ''}{total_flat_bonus}"

    if final_dice_part.startswith('+') or final_dice_part.startswith('-'):
        final_command = f"{final_base_power}{final_dice_part}"
    else:
        final_command = f"{final_base_power}+{final_dice_part}"

    tokens = re.split(r'([+-])', final_command)
    range_min = 0
    range_max = 0
    current_sign = 1

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token == '+':
            current_sign = 1
            continue
        if token == '-':
            current_sign = -1
            continue

        dice_match = re.match(r'^(\d+)d(\d+)$', token)
        if dice_match:
            num = int(dice_match.group(1))
            sides = int(dice_match.group(2))
            d_min = num
            d_max = num * sides
            if current_sign == 1:
                range_min += d_min
                range_max += d_max
            else:
                range_min -= d_max
                range_max -= d_min
            continue

        try:
            val = int(token)
            range_min += current_sign * val
            range_max += current_sign * val
        except ValueError:
            pass

    skill_details['range_min'] = range_min
    skill_details['range_max'] = range_max

    dice_term_sources = []
    try:
        for m in re.finditer(r'([+-]?)(\d+)d(?:\{([^}]+)\}|(\d+))', str(dice_part or '')):
            key = str((m.group(3) or '')).strip()
            if key == '物理補正':
                dice_term_sources.append('physical')
            elif key == '魔法補正':
                dice_term_sources.append('magical')
            elif key == 'ダイス威力':
                dice_term_sources.append('dice_stat')
            else:
                dice_term_sources.append('dice')
    except Exception:
        dice_term_sources = []

    power_breakdown = {
        "base_power": raw_base_power,
        "base_power_mod": total_base_mod,
        "base_power_buff_mod": base_power_buff_mod,
        "external_base_power_mod": _to_int(external_base_power_mod),
        "temp_base_power_mod": temp_base_power_mod,
        "final_base_power": final_base_power,
        "rule_power_bonus": rule_base_bonus,
        "buff_power_bonus": _to_int(buff_bonus_parts.get("base", 0)),
        "rule_final_power_bonus": rule_final_bonus,
        "buff_final_power_bonus": _to_int(buff_bonus_parts.get("final", 0)),
        "external_final_power_mod": _to_int(external_final_power_mod),
        "temp_final_power_mod": temp_final_power_mod,
        "wadatsumi_bonus": wadatsumi_bonus,
        "valvile_correction": valvile_correction,
        "final_power_mod": final_power_bonus,
        "rule_dice_bonus_power": rule_dice_bonus,
        "buff_dice_bonus_power": _to_int(buff_bonus_parts.get("dice", 0)),
        "dice_bonus_power": dice_bonus_power,
        "senritsu_dice_reduction": senritsu_dice_reduction,
        "physical_correction": delta_phys,
        "magical_correction": delta_mag,
        "dice_stat_correction": delta_dice_pow,
        "additional_power": total_flat_bonus,
        "total_flat_bonus": total_flat_bonus,
        "dice_term_sources": dice_term_sources,
        "selected_power_param": selected_power_param,
        "selected_power_value": selected_power_value,
    }

    return {
        "final_command": final_command,
        "min_damage": range_min,
        "max_damage": range_max,
        "damage_range_text": f"{range_min} ~ {range_max}",
        "correction_details": correction_details,
        "senritsu_dice_reduction": senritsu_dice_reduction,
        "skill_details": skill_details,
        "power_breakdown": power_breakdown,
    }


def build_power_result_snapshot(preview_data, roll_result):
    """
    プレビュー時の内訳とロール結果を統合し、確定威力の参照データを返す。
    """
    preview_data = preview_data if isinstance(preview_data, dict) else {}
    roll_result = roll_result if isinstance(roll_result, dict) else {}
    power_breakdown = preview_data.get("power_breakdown", {}) if isinstance(preview_data.get("power_breakdown"), dict) else {}
    roll_breakdown = roll_result.get("breakdown", {}) if isinstance(roll_result.get("breakdown"), dict) else {}

    def _to_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    final_power = _to_int(roll_result.get("total", 0))
    final_base_power = _to_int(power_breakdown.get("final_base_power", 0))

    dice_power = _to_int(roll_breakdown.get("dice_total", 0))
    constant_power = _to_int(roll_breakdown.get("constant_total", 0))
    if dice_power == 0 and final_power != 0 and constant_power != 0:
        dice_power = final_power - constant_power

    dice_terms = roll_breakdown.get("dice_terms", []) if isinstance(roll_breakdown.get("dice_terms"), list) else []
    dice_term_sources = power_breakdown.get("dice_term_sources", []) if isinstance(power_breakdown.get("dice_term_sources"), list) else []
    physical_dice_power = 0
    magical_dice_power = 0
    dice_stat_dice_power = 0
    generic_dice_power = 0
    if dice_terms:
        for idx, term in enumerate(dice_terms):
            if not isinstance(term, dict):
                continue
            sign = _to_int(term.get("sign", 1), 1)
            term_sum = _to_int(term.get("sum", 0))
            signed_sum = sign * term_sum
            source = str(dice_term_sources[idx]).strip().lower() if idx < len(dice_term_sources) else 'dice'
            if source == 'physical':
                physical_dice_power += signed_sum
            elif source == 'magical':
                magical_dice_power += signed_sum
            elif source == 'dice_stat':
                dice_stat_dice_power += signed_sum
            else:
                generic_dice_power += signed_sum
        # If roll breakdown had extra dice terms (or source parse failed), keep consistency.
        classified_total = physical_dice_power + magical_dice_power + dice_stat_dice_power + generic_dice_power
        if classified_total != dice_power:
            generic_dice_power += (dice_power - classified_total)
    else:
        generic_dice_power = dice_power

    snapshot = {
        "base_power_after_mod": final_base_power,
        "dice_power_after_roll": generic_dice_power + dice_stat_dice_power,
        "physical_power": physical_dice_power if dice_terms else _to_int(power_breakdown.get("physical_correction", 0)),
        "magical_power": magical_dice_power if dice_terms else _to_int(power_breakdown.get("magical_correction", 0)),
        "dice_stat_power": _to_int(power_breakdown.get("dice_stat_correction", 0)),
        "flat_power_bonus": _to_int(power_breakdown.get("total_flat_bonus", power_breakdown.get("additional_power", 0))),
        "final_power": final_power,
        "constant_power_after_roll": constant_power,
        "selected_power_param": power_breakdown.get("selected_power_param"),
        "selected_power_value": _to_int(power_breakdown.get("selected_power_value", 0)),
        "raw": {
            "preview": preview_data,
            "roll": roll_result,
            "power_breakdown": power_breakdown,
            "roll_breakdown": roll_breakdown,
        }
    }
    return snapshot


def _resolve_buff_multiplier_value(buff_entry, keys):
    if not isinstance(buff_entry, dict):
        return None
    for key in keys:
        if key in buff_entry:
            try:
                return float(buff_entry.get(key))
            except Exception:
                pass
    data = buff_entry.get('data')
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                try:
                    return float(data.get(key))
                except Exception:
                    pass
    effect_data = _resolve_runtime_buff_effect_data(buff_entry)
    if isinstance(effect_data, dict):
        for key in keys:
            if key in effect_data:
                try:
                    return float(effect_data.get(key))
                except Exception:
                    pass
    return None


def _resolve_buff_condition_value(buff_entry):
    if not isinstance(buff_entry, dict):
        return None
    condition = buff_entry.get('condition')
    if isinstance(condition, dict):
        return condition
    data = buff_entry.get('data')
    if isinstance(data, dict):
        condition = data.get('condition')
        if isinstance(condition, dict):
            return condition
    effect_data = _resolve_runtime_buff_effect_data(buff_entry)
    if isinstance(effect_data, dict):
        condition = effect_data.get('condition')
        if isinstance(condition, dict):
            return condition
    return None


def compute_damage_multipliers(attacker, defender, context=None):
    """
    与ダメ(outgoing) と被ダメ(incoming) の倍率を一括計算する。
    Returns:
        {
            "outgoing": float,
            "incoming": float,
            "final": float,
            "outgoing_logs": list[str],
            "incoming_logs": list[str],
        }
    """
    _ = context
    outgoing = 1.0
    incoming = 1.0
    outgoing_logs = []
    incoming_logs = []

    for buff in (defender or {}).get('special_buffs', []):
        if not isinstance(buff, dict):
            continue
        buff_name = str(buff.get('name', '') or '').strip()
        condition = _resolve_buff_condition_value(buff)
        if condition and not check_condition(condition, defender, attacker, context=context):
            continue

        if buff_name == "混乱":
            incoming *= 1.5
            incoming_logs.append("混乱")

        incoming_value = _resolve_buff_multiplier_value(
            buff,
            keys=['incoming_damage_multiplier', 'damage_multiplier'],
        )
        if incoming_value is not None and incoming_value != 1.0:
            incoming *= incoming_value
            if buff_name:
                incoming_logs.append(buff_name)

    for buff in (attacker or {}).get('special_buffs', []):
        if not isinstance(buff, dict):
            continue
        buff_name = str(buff.get('name', '') or '').strip()
        condition = _resolve_buff_condition_value(buff)
        if condition and not check_condition(condition, attacker, defender, context=context):
            continue
        outgoing_value = _resolve_buff_multiplier_value(
            buff,
            keys=['outgoing_damage_multiplier'],
        )
        if outgoing_value is not None and outgoing_value != 1.0:
            outgoing *= outgoing_value
            if buff_name:
                outgoing_logs.append(buff_name)

    return {
        "outgoing": outgoing,
        "incoming": incoming,
        "final": outgoing * incoming,
        "outgoing_logs": outgoing_logs,
        "incoming_logs": incoming_logs,
    }


def calculate_damage_multiplier(character):
    """
    キャラクターのバフからダメージ倍率を計算する
    (混乱 + damage_multiplier)

    Args:
        character (dict): キャラクターデータ

    Returns:
        tuple: (final_multiplier, log_list)
            - final_multiplier (float): 最終的な倍率
            - log_list (list): 適用された効果の名前リスト
    """
    mult = compute_damage_multipliers(None, character)
    return mult.get("incoming", 1.0), mult.get("incoming_logs", [])

def process_on_death(room, char, username):
    """
    死亡時イベント(on_death)を処理する
    """
    if not char: return
    logs = []

    # special_buffs (またはパッシブ) に on_death があれば実行
    # パッシブは常時バフとして special_buffs に展開されている前提（ローダーの仕組み上そうなっている）

    for buff in char.get('special_buffs', []):
        effect_data = get_buff_effect(buff.get('name'))
        if not effect_data:
            if 'data' in buff: effect_data = buff['data']
            else: continue

        on_death_effects = effect_data.get('on_death', [])
        if on_death_effects:
            # 実行
            # 死んだ本人を actor として効果処理
            # ターゲットは効果定義内の target (ALL_ENEMIESなど) に依存

            # コンテキスト作成
            from manager.room_manager import get_room_state, broadcast_log, _update_char_stat
            state = get_room_state(room)
            context = {"characters": state['characters'], "room": room}

            _, l, changes = process_skill_effects(on_death_effects, "IMMEDIATE", char, None, None, context=context)

            if l:
                broadcast_log(room, f"【{char['name']} 死亡時効果】" + " ".join(l), 'state-change')

            for (c, type, name, value) in changes:
                if type == "APPLY_STATE":
                    current = get_status_value(c, name)
                    _update_char_stat(room, c, name, current + value, username=f"[{char['name']}:遺言]")
                elif type == "APPLY_BUFF":
                    apply_buff(c, name, value["lasting"], value["delay"], data=value.get("data"), count=value.get("count"))
                    broadcast_log(room, f"[{name}] が {c['name']} に付与されました。", 'state-change')
                elif type == "SUMMON_CHARACTER":
                    from manager.summons.service import apply_summon_change

                    res = apply_summon_change(room, state, c, value)
                    if res.get("ok"):
                        broadcast_log(room, res.get("message", "召喚が発生した。"), "state-change")
                    else:
                        logger.warning("[on_death summon failed] %s", res.get("message"))
                elif type == "GRANT_SKILL":
                    from manager.granted_skills.service import apply_grant_skill_change

                    grant_payload = dict(value) if isinstance(value, dict) else {}
                    if "skill_id" not in grant_payload:
                        grant_payload["skill_id"] = name
                    res = apply_grant_skill_change(room, state, char, c, grant_payload)
                    if res.get("ok"):
                        broadcast_log(room, res.get("message", "スキル付与が発生した。"), "state-change")
                    else:
                        logger.warning("[on_death grant_skill failed] %s", res.get("message"))

    # 通常ログは呼び出し元で処理済み

def process_battle_start(room, char):
    """
    戦闘突入時イベント(battle_start_effect)を処理する
    初期FP付与などに使用
    """
    if not char: return

    # パッシブ/バフチェック
    executed = False

    for buff in char.get('special_buffs', []):
        buff_name = buff.get('name')
        effect_data = get_buff_effect(buff_name)

        # effect_data自体がない場合や、battle_start_effectがない場合はスキップ
        if not effect_data:
             # ★追加: 動的バフ（輝化スキルなど）で、dataプロパティに直接定義が入っている場合
             if 'data' in buff:
                 effect_data = buff['data']
             else:
                 continue

        start_effects = effect_data.get('battle_start_effect', [])
        if start_effects:
            # 実行 (タイミングチェックは不要だが、process_skill_effectsの仕様上タイミング指定が必要ならIMMEDIATE等で代用)
            # ここではタイミングフィルタを無視するか、データ側で指定させる
            # 既存関数再利用のため、タイミングは "BATTLE_START" と仮定するが、
            # process_skill_effectsはタイミング一致を見るので、データ側にも timing: BATTLE_START が必要。
            # しかし手入力の手間を省くため、ここでは強制的に通すか、process_skill_effectsを使わずに処理する。

            # 簡易実装: ここで処理ループを回す (process_skill_effectsは条件等が複雑なので再利用したい)
            # データ側に timing: BATTLE_START を付与して渡す

            # deepcopyしてtiming注入
            import copy
            effects_to_run = copy.deepcopy(start_effects)
            for eff in effects_to_run:
                eff['timing'] = 'BATTLE_START'
                if not eff.get('target'):
                    eff['target'] = 'self'

            from manager.room_manager import get_room_state, broadcast_log, _update_char_stat
            state = get_room_state(room)
            context = {"characters": state['characters'], "room": room}

            _, l, changes = process_skill_effects(effects_to_run, "BATTLE_START", char, None, None, context=context)

            if l:
                broadcast_log(room, f"【{char['name']} 開始時効果】" + " ".join(l), 'state-change')

            for (c, type, name, value) in changes:
                if type == "APPLY_STATE":
                    current = get_status_value(c, name)
                    _update_char_stat(room, c, name, current + value, username=f"[{buff_name}]")
                elif type == "APPLY_BUFF":
                     apply_buff(c, name, value["lasting"], value["delay"], data=value.get("data"), count=value.get("count"))
                     broadcast_log(room, f"[{name}] が {c['name']} に付与されました。", 'state-change')
                elif type == "SUMMON_CHARACTER":
                     from manager.summons.service import apply_summon_change

                     res = apply_summon_change(room, state, c, value)
                     if res.get("ok"):
                         broadcast_log(room, res.get("message", "召喚が発生した。"), "state-change")
                     else:
                         logger.warning("[battle_start summon failed] %s", res.get("message"))
                elif type == "GRANT_SKILL":
                     from manager.granted_skills.service import apply_grant_skill_change

                     grant_payload = dict(value) if isinstance(value, dict) else {}
                     if "skill_id" not in grant_payload:
                         grant_payload["skill_id"] = name
                     res = apply_grant_skill_change(room, state, char, c, grant_payload)
                     if res.get("ok"):
                         broadcast_log(room, res.get("message", "スキル付与が発生した。"), "state-change")
                     else:
                         logger.warning("[battle_start grant_skill failed] %s", res.get("message"))

            executed = True

    if executed:
        from manager.room_manager import save_specific_room_state, broadcast_state_update
        save_specific_room_state(room)
        broadcast_state_update(room)
