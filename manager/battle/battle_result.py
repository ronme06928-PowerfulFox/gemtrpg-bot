"""Determine the battle result from surviving allies and enemies."""


def _canonical_side(raw):
    text = str(raw or '').strip().lower()
    if text in {'ally', 'player', 'friend', 'friends'}:
        return 'ally'
    if text in {'enemy', 'foe', 'opponent', 'boss', 'npc'}:
        return 'enemy'
    return None


def _hit_points(value):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def estimate_battle_result(state):
    allies_alive = False
    enemies_alive = False
    for char in (state.get('characters') or []):
        if not isinstance(char, dict):
            continue
        side = (
            _canonical_side(char.get('type'))
            or _canonical_side(char.get('team'))
            or _canonical_side(char.get('side'))
            or _canonical_side(char.get('faction'))
        )
        hp = _hit_points(char.get('hp'))
        if side == 'ally' and hp > 0:
            allies_alive = True
        elif side == 'enemy' and hp > 0:
            enemies_alive = True
    if allies_alive and not enemies_alive:
        return 'ally_win'
    if enemies_alive and not allies_alive:
        return 'enemy_win'
    if not allies_alive and not enemies_alive:
        return 'draw'
    return 'in_progress'
