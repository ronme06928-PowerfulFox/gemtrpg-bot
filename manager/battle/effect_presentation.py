"""演出用の記録を組み立てる。ゲームの状態は変更しない。"""
import copy
from contextlib import contextmanager
from contextvars import ContextVar

from manager.battle.effect_glossary_map import effect_term, CUSTOM_EFFECT_TERMS
from manager.battle.skill_rules import _has_skill_tag

_step_effects = ContextVar('presentation_step_effects', default=None)
GRANT_STATES = {'出血', '破裂', '亀裂', '戦慄', '荊棘', '荊棘重絡', '凝魔', '蓄力'}


@contextmanager
def step_effects_scope():
    """解決の全体を包む。範囲の外では段の記録先を持たず、並行・入れ子の解決で記録先を混ぜない。"""
    token = _step_effects.set({'current': None})
    try:
        yield
    finally:
        _step_effects.reset(token)


def start_step_effects():
    """解決の1段の記録の一覧を作る。範囲の中なら、ループの外（威力ロール・被ダメージ反応・死亡時効果）もここへ積む。"""
    fired_effects = []
    box = _step_effects.get()
    if box is not None:
        box['current'] = fired_effects
    return fired_effects


def end_step_effects():
    box = _step_effects.get()
    if box is not None:
        box['current'] = None


def step_effects_collector():
    box = _step_effects.get()
    return box['current'] if box is not None else None


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
        "kind": "effect", "term_id": term[0], "name": term[1], "actor_id": actor.get("id"), "target_id": target.get("id"),
        "results": [r for r in results if r["delta"]],
    })


def grant_recording_before(context, session):
    if isinstance(context, dict) and isinstance(context.get('fired_effects'), list):
        return copy.deepcopy(session.simulated_chars)
    return None


def _grant_buff_status(name, payload):
    from manager.battle.skill_effect_helpers import normalize_buff_name

    buff_id = (payload.get('data') or {}).get('buff_id')
    if buff_id == 'Bu-Fissure':
        return '亀裂'
    return {'Bu-31': '凝魔', 'Bu-30': '蓄力'}.get(buff_id, normalize_buff_name(name))


def _grant_name(status, char):
    from manager.battle.skill_effect_helpers import find_sim_buff, read_stack_variant, is_chikuryoku_burst_guidance_variant
    from manager.buff_catalog import get_buff_by_id

    variant = read_stack_variant(find_sim_buff(char, status)).lower()
    view_id = None
    if status == '凝魔' and variant == 'blood_plasma':
        view_id = 'Bu-48'
    elif status == '蓄力' and is_chikuryoku_burst_guidance_variant(variant):
        view_id = 'Bu-49'
    catalog = get_buff_by_id(view_id) if view_id else None
    return (catalog.get('display_name') or catalog.get('name') or status) if catalog else status


def _amount(char, status):
    from manager.utils import get_status_value
    from manager.battle.skill_effect_helpers import resolve_buff_count

    stacks = 0
    if status in {'凝魔', '蓄力'}:
        for buff in char.get('special_buffs', []):
            data = {**(buff.get('data') or {})}
            data['buff_id'] = buff.get('buff_id') or data.get('buff_id')
            if _grant_buff_status(buff.get('name'), {'data': data}) == status:
                stacks += resolve_buff_count(buff, default=0)
    return int(get_status_value(char, status) or 0) + stacks


def _confused(char):
    return any('混乱' in str(b.get('name')) for b in char.get('special_buffs', []))


def _append_gain(fired_effects, actor_id, target_id, status, char, old, new):
    """付与1件を積む。混乱は新しく付いたときだけW-10として積む。"""
    if status == '混乱':
        import extensions
        name = str(extensions.all_glossary_data.get('W-10', {}).get('display_name') or '').strip()
        if not old and new and name:
            fired_effects.append(dict(kind='effect', term_id='W-10', name=name,
                                      actor_id=actor_id, target_id=target_id, results=[]))
    elif new - old > 0:
        fired_effects.append(dict(kind='grant', actor_id=actor_id, target_id=target_id,
                                  name=_grant_name(status, char), status=status, delta=new - old))


def snapshot_gains(chars):
    """ループの外で状態を直接書き換える処理の前に取る。段の記録先がなければNone。"""
    if step_effects_collector() is None:
        return None
    return [(char, {status: _amount(char, status) for status in GRANT_STATES}, _confused(char))
            for char in chars if isinstance(char, dict)]


def record_gains(actor_id, snapshot):
    """snapshot_gainsの後で増えた分を、段の記録先へ積む。"""
    fired_effects = step_effects_collector()
    if snapshot is None or fired_effects is None:
        return
    for char, amounts, confused in snapshot:
        for status in sorted(GRANT_STATES):
            _append_gain(fired_effects, actor_id, char.get('id'), status, char, amounts[status], _amount(char, status))
        _append_gain(fired_effects, actor_id, char.get('id'), '混乱', char, confused, _confused(char))


def record_grants(context, actor_id, before, changes):
    """1ハンドラの変更列を写しへ適用する。消費のremove/reapplyは増加と数えない。"""
    if before is None:
        return
    from manager.utils import get_status_value, set_status_value, apply_buff, remove_buff

    shadows, removed = {}, {}
    for char, kind, name, value in changes:
        if not isinstance(char, dict):
            continue
        cid = char.get('id')
        if cid not in shadows:
            shadows[cid] = copy.deepcopy(before.get(cid, char))
        shadow = shadows[cid]
        if kind in {'APPLY_STATE', 'SET_STATUS'}:
            status = name
        elif kind in {'APPLY_BUFF', 'REMOVE_BUFF'}:
            status = _grant_buff_status(name, value if isinstance(value, dict) else {})
            if '混乱' in str(name):
                status = '混乱'
        else:
            continue
        if status not in GRANT_STATES and status != '混乱':
            continue
        key = (cid, status)
        old = _confused(shadow) if status == '混乱' else _amount(shadow, status)
        if kind in {'APPLY_STATE', 'SET_STATUS'}:
            current = get_status_value(shadow, name)
            set_status_value(shadow, name, int(value) if kind == 'SET_STATUS' else current + int(value))
        elif kind == 'REMOVE_BUFF':
            removed[key] = old
            remove_buff(shadow, name)
            continue
        else:
            apply_buff(shadow, name, value['lasting'], value['delay'], data=copy.deepcopy(value.get('data')),
                       count=value.get('count'))
            # 残スタックを置き直す変更列は、取り除く前の値から増えた場合だけ付与。
            old = max(old, removed.pop(key, old))
        new = _confused(shadow) if status == '混乱' else _amount(shadow, status)
        _append_gain(context['fired_effects'], actor_id, cid, status, shadow, old, new)


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
