"""Finalize the floor specific to Valwaire's already-applied power correction."""
from manager.utils import get_effective_origin_id


def apply_origin_power_floor(roll_result, target):
    if get_effective_origin_id(target) != 13:
        return roll_result
    old = int(roll_result.get('total', 0))
    if old >= 1:
        return roll_result
    roll_result['total'] = 1
    roll_result['details'] = f"{roll_result.get('details', '')} [畏怖の衣:下限1]"
    breakdown = roll_result.get('breakdown')
    if isinstance(breakdown, dict):
        breakdown['final_total'] = 1
        breakdown['constant_total'] = int(breakdown.get('constant_total', 0)) + 1 - old
    return roll_result
