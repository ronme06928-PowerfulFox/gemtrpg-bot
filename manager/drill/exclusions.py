"""Explain effects deliberately not executed by the first-clash estimate."""
from manager.battle.match_rules import is_hard_skill, is_unmatchable_skill
from manager.battle.skill_rules import _extract_rule_data_from_skill
from manager.buff_catalog import resolve_runtime_buff_effect
from manager.utils import (get_effective_origin_id, ORIGIN_FLODIAS, ORIGIN_EMRIDA,
                           ORIGIN_GRAND_LITTERAL_BLANC)
from plugins.buffs.registry import buff_registry


def excluded_effects(actor, target, skill_a, skill_d):
    result = []
    mutual = is_unmatchable_skill(skill_a) or is_unmatchable_skill(skill_d)

    def note(side, code, reason):
        row = {'side':side, 'code':code, 'reason':reason}
        if row not in result:
            result.append(row)

    for side, char, skill in [('actor',actor,skill_a), ('target',target,skill_d)]:
        if skill:
            rule = _extract_rule_data_from_skill(skill)
            for effect in rule.get('effects', []):
                if not isinstance(effect, dict):
                    continue
                timing, effect_type = effect.get('timing', '?'), effect.get('type', '?')
                note(side, 'skill_effect', f"{skill.get('id', '')}: {timing}/{effect_type}の発動・状態変化・追加ダメージは含みません。")
            if is_hard_skill(skill):
                note(side, 'hard_followup', '強硬の敗北後の追撃と回避の再ロールは含みません。')
            if rule.get('cost'):
                note(side, 'cost_state', 'コストの支払いによる参照値の変化は含みません。入力の現在値で計算します。')
            if _needs_room(rule.get('power_bonus', [])):
                note(side, 'room_context', '相手スキル・ラウンド・他のキャラクター・行動順など、プレビューに渡らない条件は含みません。')
        for buff in char.get('special_buffs', []):
            effect = resolve_runtime_buff_effect(buff) or {}
            for key in ('on_damage_state', 'on_damage_reaction', 'effects', 'on_hit'):
                if effect.get(key):
                    note(side, 'buff_reaction', f"{buff.get('name') or buff.get('buff_id')}: {key}の発動は含みません。")
            handler = buff_registry.get_handler(buff.get('buff_id'))
            if handler and hasattr(handler, 'on_hit_damage_calculation'):
                note(side, 'buff_on_hit', f"{buff.get('name') or buff.get('buff_id')}: 的中時の追加ダメージ・消費は含みません。")
            condition = buff.get('condition') or effect.get('condition')
            if mutual and isinstance(condition,dict) and condition.get('param') in ('HP','MP','FP'):
                note(side, 'mutual_state', '相互一方攻撃の途中のHP等の変化による倍率条件の再判定は含みません。')
            if _needs_room(effect.get('power_bonus', [])) or _needs_room(condition):
                note(side, 'room_context', 'バフのルーム・行動順の条件はルームなしの現在値で評価します。')
        if char.get('SPassive'):
            note(side, 'passive_activation', '特殊パッシブ・輝化の発動や状態変化は実行しません。現在の補正は含みます。')
        if get_effective_origin_id(char) == 8:
            note(side, 'origin_counter', '反撃の石の防御勝利後の追加ダメージは含みません。')
        if get_effective_origin_id(char) in (ORIGIN_FLODIAS, ORIGIN_EMRIDA):
            note(side, 'origin_room', '出身の他者・同速度判定は入力の2人だけで評価し、ルームの他のキャラクターは含みません。')
        if get_effective_origin_id(char) == ORIGIN_GRAND_LITTERAL_BLANC:
            note(side, 'origin_hit', '出身の的中後の色彩付与は実行しません。現在の色彩による補正は含みます。')
        for state in char.get('states', []):
            if state.get('name') in ('荊棘', '出血', '破裂') and float(state.get('value', 0) or 0) > 0:
                note(side, 'state_reaction', f"{state['name']}の自傷・消費・反応は含みません。")
    return result


def _needs_room(value):
    if isinstance(value, list):
        return any(_needs_room(row) for row in value)
    if not isinstance(value, dict):
        return False
    if value.get('source') not in (None, 'self', 'target', 'skill', 'actor_skill'):
        return True
    if any(key in value for key in ('round', 'timeline', 'characters', 'allies', 'enemies')):
        return True
    return any(_needs_room(row) for row in value.values() if isinstance(row, (dict, list)))
