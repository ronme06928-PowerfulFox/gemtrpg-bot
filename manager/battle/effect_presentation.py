"""演出用の記録を組み立てる。ゲームの状態は変更しない。"""
import copy
from contextlib import contextmanager
from contextvars import ContextVar

from manager.battle.effect_glossary_map import effect_term, CUSTOM_EFFECT_TERMS
from manager.battle.skill_rules import _has_skill_tag

_power_effects = ContextVar('presentation_power_effects', default=None)


@contextmanager
def capture_power_effects(fired_effects):
    """威力ロールの既存APIを保ち、ネスト・並行した解決で記録先を混ぜない。"""
    token = _power_effects.set(fired_effects)
    try:
        yield
    finally:
        _power_effects.reset(token)


def power_effects_collector():
    return _power_effects.get()


def recording_before(context, char, effect):
    if not isinstance(context, dict) or not isinstance(context.get('fired_effects'), list):
        return None
    kind, value = effect.get('type', 'CUSTOM_EFFECT'), effect.get('value')
    mapped_custom = kind == 'CUSTOM_EFFECT' and isinstance(value, str) and value in CUSTOM_EFFECT_TERMS
    if not mapped_custom and kind not in {'USE_SKILL_AGAIN', 'CONVERT_STACK_RESOURCE_VARIANT'}:
        return None
    return copy.deepcopy(char)


def record_fired_effect(context, effect, actor, target, before, changes, converted_resource=None):
    if before is None or not isinstance(context.get("fired_effects"), list):
        return
    term = effect_term(effect, converted_resource)
    if not term or (not changes and converted_resource is None):
        return
    from manager.utils import get_status_value

    values = {}
    results = []
    for char, kind, name, value in changes:
        if not isinstance(char, dict) or str(char.get("id")) != str(target.get("id")) or str(name).upper() == "HP":
            continue
        if kind in {"APPLY_STATE", "SET_STATUS"}:
            old = values.get(name, int(get_status_value(before, name) or 0))
            new = max(0, int(value) if kind == "SET_STATUS" else old + int(value))
            if name == "MP" and before.get("maxMp") is not None:
                new = min(new, int(before["maxMp"]))
            values[name] = new
        elif kind == 'CONSUME_BLEED_MAINTENANCE':
            from manager.bleed_logic import get_bleed_maintenance_count
            name = 'buff:出血遷延'
            old = values.get(name, get_bleed_maintenance_count(before))
            new = max(0, old - int(value))
            values[name] = new
        elif kind in {"APPLY_BUFF", "REMOVE_BUFF"}:
            name = f"buff:{name}"
            old = values.get(name, sum(int(b.get("count", (b.get("data") or {}).get("count", 1)) or 0)
                                       for b in before.get("special_buffs", []) if f"buff:{b.get('name')}" == name))
            new = old + int(value.get("count", (value.get("data") or {}).get("count", 1)) or 0) if kind == "APPLY_BUFF" else 0
            if kind == 'APPLY_BUFF' and '混乱' in name:
                new = max(old, 1)
            values[name] = new
        else:
            continue
        if new != old:
            existing = next((r for r in results if r["name"] == name), None)
            if existing:
                existing["delta"] += new - old
            else:
                results.append({"name": name, "delta": new - old})
    context["fired_effects"].append({
        "term_id": term[0], "name": term[1], "actor_id": actor.get("id"), "target_id": target.get("id"),
        "results": [r for r in results if r["delta"]],
    })


def will_self_destruct(actor, skill):
    return (isinstance(actor, dict) and int(actor.get("hp", 0) or 0) > 0
            and (_has_skill_tag(skill, "自滅") or _has_skill_tag(skill, "自壊")))


def self_destruct_ids(*actor_skill_pairs):
    return [actor["id"] for actor, skill in actor_skill_pairs if will_self_destruct(actor, skill)]


def mass_effect_applied(diff, damage_events, fired_effects):
    """合算の本体行はdamage_eventsにあるため、差分へ重複して入れない。"""
    damage = []
    for row in diff.get('damage', []):
        main = sum(int(e.get('hp', 0)) for e in damage_events if e.get('target_id') == row.get('target_id'))
        extra = int(row['hp']) - main
        if extra > 0:
            damage.append({**row, 'hp': extra})
    return {**diff, 'damage': damage, 'fired_effects': fired_effects}
