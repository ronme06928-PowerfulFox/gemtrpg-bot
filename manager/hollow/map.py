"""Deterministic ten-floor maps, topped by a start node, and weighted draws for an expedition."""

from math import floor

FLOORS_PER_TIER = 10
SIGHT = 2
EVENT_WEIGHTS = (("battle", "normal"), ("elite", "elite"))
_MASK = 0xffffffff


def weighted_choice(options, rng):
    choices = [(value, weight) for value, weight in options if weight > 0]
    if not choices:
        raise ValueError("抽選できる重みがありません")
    roll = rng.randrange(sum(weight for _, weight in choices))
    for value, weight in choices:
        if roll < weight:
            return value
        roll -= weight


def _map_random(seed):
    # Match the prototype's 32-bit Mulberry32 stream.
    while True:
        seed = (seed + 0x6D2B79F5) & _MASK
        value = ((seed ^ (seed >> 15)) * (1 | seed)) & _MASK
        value = ((value + (value ^ (value >> 7)) * (61 | value)) ^ value) & _MASK
        yield (value ^ (value >> 14)) / (1 << 32)


def _connect(rows, following, rng):
    left = right = 0
    rows[left]["next"].append(following[right]["id"])
    while left < len(rows) - 1 or right < len(following) - 1:
        can_left = left < len(rows) - 1
        can_right = right < len(following) - 1
        lag = left / max(len(rows) - 1, 1) - right / max(len(following) - 1, 1)
        roll = next(rng)
        if can_left and can_right and abs(lag) <= .34 and roll < .55:
            left += 1
            right += 1
        elif can_left and (not can_right or lag < -.34 or (abs(lag) <= .34 and roll < .775)):
            left += 1
        else:
            right += 1
        rows[left]["next"].append(following[right]["id"])


def build_map(tier, area, fixed_floors, seed):
    rng = _map_random(seed)
    number = tier["tier"]
    start = FLOORS_PER_TIER * (number - 1)
    weights = [(kind, area["event_weights"].get(key, 0)) for kind, key in EVENT_WEIGHTS]
    total = sum(weight for _, weight in weights)
    if total <= 0:
        raise ValueError("抽選できる重みがありません")
    # The prototype draws elite below its threshold.
    elite_ratio = weights[1][1] / total
    entry = {"id": f"n{start}s", "floor": start, "type": "start", "shift": 0, "next": []}
    rows = []
    for index in range(1, FLOORS_PER_TIER + 1):
        floor_number = start + index
        fixed = fixed_floors.get(floor_number)
        boss = index == FLOORS_PER_TIER
        roll = next(rng)
        width = 1 if fixed or boss or roll < .06 else 2 if roll < .5 else 3
        row = [{"id": f"n{floor_number}{chr(97 + column)}", "floor": floor_number,
                "type": "boss" if boss else "elite" if next(rng) < elite_ratio else "battle",
                "shift": 0 if boss else floor((next(rng) - .5) * 40 + .5), "next": []}
               for column in range(width)]
        if rows:
            _connect(rows[-1], row, rng)
        rows.append(row)
    entry["next"] = [node["id"] for node in rows[0]]
    return {"tier": number, "name": tier.get("name", ""), "seed": seed,
            "rows": [[entry], *rows], "current": entry["id"], "visited": [entry["id"]]}


def project_map(layout, current_floor):
    """Remove unseen nodes, links to them, and the seed from a room payload."""
    last = layout["tier"] * FLOORS_PER_TIER
    visible_through = current_floor + SIGHT
    rows = [row for row in layout["rows"] if row[0]["floor"] <= visible_through]
    visible_ids = {node["id"] for row in rows for node in row}
    return {"tier": layout["tier"], "map_id": layout["map_id"], "name": layout.get("name", ""), "last_floor": last,
            "current": layout["current"], "visited": [key for key in layout["visited"] if key in visible_ids],
            "rows": [[{**node, "next": [key for key in node["next"] if key in visible_ids]}
                      for node in row] for row in rows]}


def next_nodes(layout):
    return node_at(layout, layout["current"])["next"]


def node_at(layout, node_id):
    return next((node for row in layout["rows"] for node in row if node["id"] == node_id), None)
