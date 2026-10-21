"""Valwaire's final-power correction: -1, but never lowers a power below 1."""
from manager.utils import get_effective_origin_id


def valwaire_corrected_total(total):
    """補正前の値に−1を適用する。補正前2以上は最低1、補正前1以下は変えない。"""
    total = int(total)
    return total - 1 if total > 1 else total


def valwaire_floor_after_correction(total):
    """−1済みの値について、補正前が1以下だった分を戻す（下限で引き上げない）。"""
    total = int(total)
    return min(total + 1, 1) if total < 1 else total


def apply_origin_power_floor(roll_result, target):
    """プレビューで−1済みの値について、補正前が1以下だった分を戻す。"""
    if get_effective_origin_id(target) != 13:
        return roll_result
    old = int(roll_result.get('total', 0))
    new = valwaire_floor_after_correction(old)
    if new == old:
        return roll_result
    roll_result['total'] = new
    roll_result['details'] = f"{roll_result.get('details', '')} [畏怖の衣:下限1]"
    breakdown = roll_result.get('breakdown')
    if isinstance(breakdown, dict):
        breakdown['final_total'] = new
        breakdown['constant_total'] = int(breakdown.get('constant_total', 0)) + new - old
    return roll_result
