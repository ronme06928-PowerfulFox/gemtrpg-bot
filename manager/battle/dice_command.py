import re


def apply_dice_power_bonus_to_command(command, dice_power_bonus):
    try:
        bonus = int(dice_power_bonus or 0)
    except (TypeError, ValueError):
        bonus = 0

    if bonus == 0 or not isinstance(command, str):
        return command

    def _replace(match):
        sign = match.group(1) or ''
        count = match.group(2)
        faces = max(1, int(match.group(3)) + bonus)
        return f"{sign}{count}d{faces}"

    return re.sub(r'([+-]?)(\d+)d(\d+)', _replace, command, count=1)
