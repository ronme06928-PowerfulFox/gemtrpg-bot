"""
Bleed resolution helpers shared by round-end flow and custom effects.
"""

from manager.utils import get_status_value

BLEED_MAINTENANCE_BUFF_ID = "Bu-08"


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def get_bleed_maintenance_count_from_buff(buff):
    """
    Resolve remaining stacks for Bu-08 style buffs.
    Legacy data without count is treated as 1 stack.
    """
    if not isinstance(buff, dict):
        return 0

    count = buff.get("count")
    if count is None and isinstance(buff.get("data"), dict):
        count = buff["data"].get("count")

    if count is None:
        # Backward compatibility for legacy definitions.
        return 1

    return max(0, _safe_int(count, 0))


def find_active_bleed_maintenance_buff(char):
    if not isinstance(char, dict):
        return None
    for buff in char.get("special_buffs", []):
        if not isinstance(buff, dict):
            continue
        if str(buff.get("buff_id", "")).strip() != BLEED_MAINTENANCE_BUFF_ID:
            continue
        if _safe_int(buff.get("delay", 0), 0) > 0:
            continue
        if get_bleed_maintenance_count_from_buff(buff) > 0:
            return buff
    return None


def get_bleed_maintenance_count(char):
    buff = find_active_bleed_maintenance_buff(char)
    if not buff:
        return 0
    return get_bleed_maintenance_count_from_buff(buff)


def consume_bleed_maintenance_stack(char, amount=1):
    """
    Consume Bu-08 stacks when a bleed damage processing event happens.
    Returns (consumed, remaining).
    """
    if amount <= 0:
        return 0, get_bleed_maintenance_count(char)

    buff = find_active_bleed_maintenance_buff(char)
    if not buff:
        return 0, 0

    current = get_bleed_maintenance_count_from_buff(buff)
    if current <= 0:
        return 0, 0

    consumed = min(int(amount), current)
    remaining = current - consumed

    if remaining > 0:
        buff["count"] = remaining
        if not isinstance(buff.get("data"), dict):
            buff["data"] = {}
        buff["data"]["count"] = remaining
    else:
        buffs = char.get("special_buffs", [])
        for idx, row in enumerate(list(buffs)):
            if row is buff:
                del buffs[idx]
                break

    return consumed, remaining


def resolve_bleed_tick(char, *, consume_maintenance=True):
    """
    Resolve one bleed damage-processing event.

    Returns:
      {
        "damage": int,
        "bleed_before": int,
        "bleed_after": int,
        "bleed_delta": int,
        "maintenance_before": int,
        "maintenance_consumed": int,
        "maintenance_remaining": int,
      }
    """
    bleed_before = max(0, _safe_int(get_status_value(char, "出血"), 0))
    if bleed_before <= 0:
        return {
            "damage": 0,
            "bleed_before": 0,
            "bleed_after": 0,
            "bleed_delta": 0,
            "maintenance_before": get_bleed_maintenance_count(char),
            "maintenance_consumed": 0,
            "maintenance_remaining": get_bleed_maintenance_count(char),
        }

    maintenance_before = get_bleed_maintenance_count(char)
    maintenance_consumed = 0
    maintenance_remaining = maintenance_before

    if consume_maintenance and maintenance_before > 0:
        maintenance_consumed, maintenance_remaining = consume_bleed_maintenance_stack(char, 1)

    if maintenance_consumed > 0:
        bleed_after = bleed_before
    else:
        bleed_after = bleed_before // 2

    return {
        "damage": bleed_before,
        "bleed_before": bleed_before,
        "bleed_after": bleed_after,
        "bleed_delta": bleed_after - bleed_before,
        "maintenance_before": maintenance_before,
        "maintenance_consumed": maintenance_consumed,
        "maintenance_remaining": maintenance_remaining,
    }

