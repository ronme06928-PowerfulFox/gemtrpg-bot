"""Exact joint distributions of the initial duel, without executing effects."""
from collections import Counter
from copy import deepcopy
from fractions import Fraction
import math

from extensions import all_skill_data
from manager.game_logic import calculate_skill_preview, compute_damage_multipliers, get_status_value
from manager.battle.match_rules import MatchRules, scale_damage, finish_damage
from manager.battle.origin_power import apply_origin_power_floor
from manager.battle.skill_rules import _extract_rule_data_from_skill
from .distribution import dice_distribution, MAX_PAIRS
from .exclusions import excluded_effects
from .validation import validate_snapshot, skill_id as validate_skill_id


def advantage(rate):
    if not math.isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError('勝率は0〜1で指定してください。')
    rate = rate if isinstance(rate, Fraction) else Fraction(str(rate))
    if rate >= Fraction(4,5):
        return '非常に有利'
    if rate >= Fraction(3,5):
        return '有利'
    if rate > Fraction(2,5):
        return '拮抗'
    if rate > Fraction(1,5):
        return '不利'
    return '非常に不利'


def _skill(key):
    if key is None:
        return None
    if key not in all_skill_data:
        raise ValueError(f'スキルがありません: {key}')
    return {**deepcopy(all_skill_data[key]), 'id':key}


def _power(actor, target, skill):
    if skill is None:
        return Counter({0:1}), 1, '0'
    # Temporary legacy execution bonuses are reset by execute_duel_match.
    actor['_base_power_bonus'] = actor['_final_power_bonus'] = 0
    preview = calculate_skill_preview(actor, target, skill,
        rule_data=_extract_rule_data_from_skill(skill),
        context={'actor_skill_data':skill, 'characters':[actor,target]})
    command = preview['final_command']
    counts, total = dice_distribution(command)
    adjusted = Counter()
    for power, ways in counts.items():
        adjusted[apply_origin_power_floor({'total':power}, target)['total']] += ways
    return adjusted, total, command


def _rows(counts, total):
    return [{'value':power, 'probability':ways / total} for power, ways in sorted(counts.items())] if total else []


def _damage(decision, raw, hit, half, fissure, multiplier):
    if not hit:
        return 0
    amount = scale_damage(raw + fissure, multiplier)
    if decision.branch == 'unmatchable':
        return amount if raw + fissure > 0 else 0
    if decision.branch == 'incapacitated':
        return amount
    return finish_damage(amount, feint=half)


def calculate_match(actor, target, skill_id, target_skill_id=None, *, trusted=False):
    # 入力の大きさの上限は外から受けた値のためのもの。ルームの値（trusted）には掛けない。
    if not trusted:
        validate_snapshot(actor)
        validate_snapshot(target)
        validate_skill_id(skill_id)
        validate_skill_id(target_skill_id, optional=True)
    actor, target = deepcopy(actor), deepcopy(target)
    if not actor.get('id') or not target.get('id') or actor.get('id') == target.get('id'):
        actor['id'], target['id'] = '__drill_actor', '__drill_target'
    skill_a, skill_d = _skill(skill_id), _skill(target_skill_id)
    try:
        a, total_a, command_a = _power(actor, target, skill_a)
        d, total_d, command_d = _power(target, actor, skill_d)
        if len(a) * len(d) > MAX_PAIRS:
            raise ValueError('両者の威力の組合せは65536通りまでです。')
        rules = MatchRules(skill_a, skill_d,
            incapacitated_a=skill_id == 'S-Confusion', incapacitated_d=target_skill_id == 'S-Confusion')
        multipliers = (float(compute_damage_multipliers(target, actor)['final'] or 1.0),
                       float(compute_damage_multipliers(actor, target)['final'] or 1.0))
        if any(not math.isfinite(value) for value in multipliers):
            raise ValueError('ダメージ倍率が範囲外です。')
        fissures = (get_status_value(actor, '亀裂'), get_status_value(target, '亀裂'))
        wins = Counter()
        all_damage = [Counter(), Counter()]
        conditional = {outcome:[Counter(),Counter()] for outcome in ('win','draw','lose')}
        for pa, ways_a in a.items():
            for pd, ways_d in d.items():
                decision = rules.resolve(pa,pd)
                outcome = {1:'win', 0:'draw', -1:'lose'}[decision.winner]
                ways = ways_a * ways_d
                wins[outcome] += ways
                amounts = (_damage(decision,decision.damage_a,decision.hit_a,decision.feint_a,fissures[0],multipliers[0]),
                           _damage(decision,decision.damage_d,decision.hit_d,decision.feint_d,fissures[1],multipliers[1]))
                for side, amount in enumerate(amounts):
                    all_damage[side][amount] += ways
                    conditional[outcome][side][amount] += ways
        total = total_a * total_d
        probabilities = {outcome:wins[outcome] / total for outcome in ('win','draw','lose')}
        rate = Fraction(wins['win'] * 2 + wins['draw'], 2 * total)
        reasons = excluded_effects(actor,target,skill_a,skill_d)
        return {
            'probabilities':probabilities, 'win_rate':float(rate), 'advantage':advantage(rate),
            'commands':{'actor':command_a,'target':command_d},
            'power_distributions':{'actor':_rows(a,total_a),'target':_rows(d,total_d)},
            'damage_distributions':{
                **{side:_rows(all_damage[index],total) for index,side in enumerate(('actor','target'))},
                **{'on_'+outcome:{side:_rows(conditional[outcome][index],wins[outcome])
                    for index,side in enumerate(('actor','target'))} for outcome in ('win','draw','lose')},
            },
            'has_excluded_effects':bool(reasons), 'notice':'見込みに含まない効果あり' if reasons else '',
            'excluded_effects':reasons,
        }
    except (TypeError, AttributeError, ArithmeticError) as error:
        raise ValueError('キャラクターの値・効果・式を計算できません。') from error
