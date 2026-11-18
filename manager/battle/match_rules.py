"""Side-effect-free first-duel decisions, shared by live combat and the drill."""
from typing import NamedTuple

from manager.battle.skill_rules import _resolve_skill_role


def skill_tags(skill):
    if not isinstance(skill, dict):
        return []
    tags = list(skill.get('tags', [])) if isinstance(skill.get('tags'), list) else []
    rule = skill.get('rule_data')
    if isinstance(rule, dict) and isinstance(rule.get('tags'), list):
        tags.extend(rule['tags'])
    return [str(value).strip() for value in tags if str(value).strip()]


def is_hard_skill(skill):
    return bool(set(skill_tags(skill)) & {'強硬', '強硬スキル', 'hard_skill'})


def is_feint_skill(skill):
    return bool(set(skill_tags(skill)) & {'牽制', '牽制スキル', 'feint_skill'})


def is_normal_skill(skill):
    return not is_hard_skill(skill) and not is_feint_skill(skill)


def is_unmatchable_skill(skill):
    joined = ' '.join(skill_tags(skill))
    name = str((skill or {}).get('name') or '').lower()
    return 'unmatchable' in joined.lower() or 'マッチ不可' in joined or 'unmatchable' in name


def is_defense_or_evasion_skill(skill, skill_id=None):
    skill = skill or {}
    category = str(skill.get('分類') or skill.get('attribute') or '')
    joined = ' '.join(skill_tags(skill) + [category, str(skill.get('name') or ''), str(skill_id or '')]).lower()
    return any(token in joined for token in ('defense', 'evade', '防御', '回避', '守備'))


def is_damage_reducing_defense_skill(skill):
    return _resolve_skill_role(skill) == 'defense'


def damage_from_rolls(winner_total, loser_total, loser_skill_data):
    def number(value):
        try:
            return int(value or 0)
        except (ValueError, TypeError, OverflowError):
            return 0
    winner, loser = number(winner_total), number(loser_total)
    if is_damage_reducing_defense_skill(loser_skill_data):
        return _power_damage(winner, loser, 'defense'), '差分ダメージ'
    return _power_damage(winner, loser, 'attack'), 'ダイスダメージ'


def _power_damage(winner, loser, loser_role):
    return max(0, int(winner) - int(loser) if loser_role == 'defense' else int(winner))


def scale_damage(raw, multiplier):
    return int(int(raw or 0) * float(multiplier or 1.0))


def finish_damage(damage, *, feint=False):
    damage = int(damage or 0)
    return 0 if damage <= 0 else damage // 2 if feint else damage


def feint_damage(damage, winner_skill, loser_skill):
    return finish_damage(damage, feint=is_feint_skill(winner_skill) and is_normal_skill(loser_skill))


class MatchDecision(NamedTuple):
    branch: str
    winner: int  # 1: attacker, -1: defender, 0: no comparative winner
    damage_a: int = 0
    damage_d: int = 0
    hit_a: bool = False
    hit_d: bool = False
    feint_a: bool = False
    feint_d: bool = False


class MatchRules:
    """Resolve many power pairs without repeatedly parsing the same skill metadata."""

    def __init__(self, skill_a, skill_d, *, one_sided=False,
                 incapacitated_a=False, incapacitated_d=False):
        self.a, self.d = skill_a or {}, skill_d or {}
        self.tags_a, self.tags_d = self.a.get('tags', []), self.d.get('tags', [])
        self.cat_a = str(self.a.get('分類') or self.a.get('attribute') or '')
        self.cat_d = str(self.d.get('分類') or self.d.get('attribute') or '')
        self.role_a, self.role_d = _resolve_skill_role(self.a), _resolve_skill_role(self.d)
        self.one_sided = one_sided or skill_d is None
        self.incap_a, self.incap_d = incapacitated_a, incapacitated_d
        self.unmatchable = is_unmatchable_skill(self.a) or is_unmatchable_skill(self.d)
        self.half_a = is_feint_skill(self.d) and is_normal_skill(self.a)
        self.half_d = is_feint_skill(self.a) and is_normal_skill(self.d)
        self.no_damage_a = is_defense_or_evasion_skill(self.a, self.a.get('id'))
        self.no_damage_d = is_defense_or_evasion_skill(self.d, self.d.get('id'))

    def resolve(self, power_a, power_d):
        a, d = power_a, power_d
        if 'free_cost' in self.tags_a or 'free_cost' in self.tags_d:
            return MatchDecision('effects_only', 0)
        if self.incap_a:
            return MatchDecision('incapacitated', -1, d, 0, True)
        if self.incap_d:
            return MatchDecision('incapacitated', 1, 0, a, False, True)
        if self.one_sided:
            hit = '守備' not in self.tags_a
            return MatchDecision('one_sided', 1, 0, a if hit else 0, False, hit,
                                 False, self.half_d)
        if self.unmatchable:
            return MatchDecision('unmatchable', 0, 0 if self.no_damage_d else d,
                                 0 if self.no_damage_a else a, True, True)
        if self.cat_a == self.cat_d == '防御':
            return MatchDecision('defense_defense', 0)
        if {self.cat_a, self.cat_d} == {'防御', '回避'}:
            return MatchDecision('defense_evade', 0)
        if self.cat_a == self.cat_d == '回避':
            return MatchDecision('evade_evade', 0)
        if '守備' in self.tags_d and self.cat_d in ('防御', '回避'):
            branch = 'guard_defense' if self.cat_d == '防御' else 'guard_evade'
            return MatchDecision(branch, 1 if a > d else -1, 0,
                                 (a - d if self.cat_d == '防御' else a) if a > d else 0,
                                 False, a > d, False, self.half_d)
        if self.cat_a == '回避':
            return MatchDecision('attacker_evade', 1 if a >= d else -1,
                                 d if a < d else 0, 0, a < d, False, self.half_a)
        if a > d or (a == d and self.role_a in ('defense', 'evade')):
            hit = self.role_a not in ('defense', 'evade')
            damage = _power_damage(a, d, self.role_d) if hit else 0
            return MatchDecision('compare_attacker', 1, 0, damage, False, hit, False, self.half_d)
        if d > a or (d == a and self.role_d in ('defense', 'evade')):
            hit = self.role_d not in ('defense', 'evade')
            damage = _power_damage(d, a, self.role_a) if hit else 0
            return MatchDecision('compare_defender', -1, damage, 0, hit, False, self.half_a)
        return MatchDecision('draw', 0)


def decide_match(skill_a, skill_d, power_a, power_d, **options):
    return MatchRules(skill_a, skill_d, **options).resolve(power_a, power_d)
