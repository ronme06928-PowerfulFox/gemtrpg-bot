"""Deterministic ten-floor maps and weighted draws for an expedition."""

from random import Random

WIDTHS = (1, 2, 3, 2, 3, 1, 2, 3, 2, 1)
EVENT_WEIGHTS = (("battle", "normal"), ("elite", "elite"))


def weighted_choice(options, rng):
    choices = [(value, weight) for value, weight in options if weight > 0]
    if not choices:
        raise ValueError("抽選できる重みがありません")
    roll = rng.randrange(sum(weight for _, weight in choices))
    for value, weight in choices:
        if roll < weight:
            return value
        roll -= weight


def _connect(rows, following):
    # Evenly space the rows in the same column range regardless of width.
    def distance(left, i, right, j):
        return abs((2 * i + 1) * len(right) - (2 * j + 1) * len(left))

    incoming = set()
    for i, source in enumerate(rows):
        choices = sorted(range(len(following)), key=lambda j: (distance(rows, i, following, j), j))
        targets = choices[:1 if len(rows) == len(following) else 2]
        source["next"] = [following[j]["id"] for j in sorted(targets)]
        incoming.update(targets)
    for j in set(range(len(following))) - incoming:
        i = min(range(len(rows)), key=lambda i: distance(rows, i, following, j))
        rows[i]["next"].append(following[j]["id"])


def build_map(tier, fixed_floors, seed):
    rng = Random(seed)
    number = tier["tier"]
    start = 10 * (number - 1)
    weights = [(kind, tier["event_weights"].get(key, 0)) for kind, key in EVENT_WEIGHTS]
    rows = []
    for index, width in enumerate(WIDTHS, 1):
        floor = start + index
        fixed = fixed_floors.get(floor)
        boss = index == len(WIDTHS) or (fixed and fixed["type"] == "boss")
        row = [{"id": f"n{floor}{chr(97 + column)}", "floor": floor,
                "type": "boss" if boss else weighted_choice(weights, rng), "next": []}
               for column in range(1 if fixed or boss else width)]
        if rows:
            _connect(rows[-1], row)
        rows.append(row)
    return {"tier": number, "seed": seed, "rows": rows, "current": None, "visited": []}


def next_nodes(layout):
    current = layout["current"]
    if current is None:
        return [node["id"] for node in layout["rows"][0]]
    return node_at(layout, current)["next"]


def node_at(layout, node_id):
    return next((node for row in layout["rows"] for node in row if node["id"] == node_id), None)
