"""Reward and fusion rules. Only successful operations mutate the run."""
from collections import Counter
from random import Random

from manager.hollow.map import weighted_choice
from manager.hollow.resources import DRAW_CATEGORIES


def reward_rank_weights(tier, encounter):
    cap = min(5, tier + {"battle": 0, "elite": 1, "boss": 2}[encounter])
    return [(rank, 2 if rank == cap - 1 else 1) for rank in range(1, cap + 1)]


def draw_relic(relics, category_weights, rank, rng):
    pools = {}
    for key, item in sorted(relics.items()):
        category = item["category"]
        if category in DRAW_CATEGORIES and category_weights.get(category, 0) > 0 and item["rank"] <= rank:
            pools.setdefault(category, {}).setdefault(item["rank"], []).append(key)
    if not pools:
        return None
    category = weighted_choice([(key, category_weights[key]) for key in DRAW_CATEGORIES if key in pools], rng)
    return rng.choice(pools[category][max(pools[category])])


def reward_candidates(run, encounter, category_weights, relics):
    weights = reward_rank_weights(run["map"]["tier"], encounter)
    if not any(category_weights.get(key, 0) > 0 for key in DRAW_CATEGORIES):
        category_weights = dict.fromkeys(DRAW_CATEGORIES, 1)
    rng = Random(f"{run['seed']}:reward:{run['floor']}:{run['map']['current']}")
    remaining = dict(relics)
    result = []
    for _ in range(3):
        rank = weighted_choice(weights, rng)
        key = draw_relic(remaining, category_weights, rank, rng)
        if key is None:
            key = draw_relic(remaining, category_weights, weights[-1][0], rng)
        if key is None:
            break
        result.append(key)
        del remaining[key]
    return result


def acquire(run, key, relic, *, charge=True):
    rank = relic["rank"]
    duplicate = key in run["relics"]
    if duplicate:
        material = str(rank)
        run["materials"][material] = run["materials"].get(material, 0) + 1
    else:
        run["relics"].append(key)
    if charge:
        run["mana_load"] += rank
    return {"relic_id": key, "rank": rank, "material": duplicate}


def fusion_rank(ranks):
    return min(5, (sum(ranks) + 1) // 2)


def fusion_materials(run, payload, definitions):
    if not isinstance(payload, list) or not 2 <= len(payload) <= 4:
        raise ValueError("材料を2〜4個指定してください")
    relic_ids, materials = [], Counter()
    for row in payload:
        if isinstance(row, dict) and set(row) == {"relic_id"} and isinstance(row["relic_id"], str):
            key = row["relic_id"]
            if key not in run["relics"] or key not in definitions or key in relic_ids:
                raise ValueError("所持している異なる淵遺物を指定してください")
            relic_ids.append(key)
        elif isinstance(row, dict) and set(row) == {"rank"} and type(row["rank"]) is int and 1 <= row["rank"] <= 5:
            key = str(row["rank"])
            materials[key] += 1
            if materials[key] > run["materials"].get(key, 0):
                raise ValueError("汎用素材の所持数を超えています")
        else:
            raise ValueError("材料の指定が不正です")
    return sorted(relic_ids), materials


def matching_recipe(relic_ids, materials, recipes, active_relics):
    if materials:
        return None
    return next((row for row in recipes.values() if row["material_ids"] == relic_ids
                 and row["result_id"] in active_relics), None)


def fusion_result(run, relic_ids, materials, relics, active, recipe, wish):
    if recipe:
        return recipe["result_id"], False
    if wish is not None and (wish not in DRAW_CATEGORIES or run["fusion"]["wishes_left"] < 1):
        raise ValueError("祈念できるカテゴリと残り回数を確認してください")
    ranks = [relics[key]["rank"] for key in relic_ids]
    ranks.extend(int(rank) for rank in materials.elements())
    categories = Counter(relics[key]["category"] for key in relic_ids if relics[key]["category"] in DRAW_CATEGORIES)
    weights = ({wish: 1} if wish else categories or dict.fromkeys(DRAW_CATEGORIES, 1))
    rng = Random(f"{run['seed']}:fusion:{run['floor']}:{run['fusion']['count']}")
    result_id = draw_relic(active, weights, fusion_rank(ranks), rng)
    if result_id is None:
        raise ValueError("この材料から作れる淵遺物がありません")
    return result_id, wish is not None


def consume_materials(run, relic_ids, materials):
    run["relics"] = [key for key in run["relics"] if key not in relic_ids]
    for rank, amount in materials.items():
        remaining = run["materials"][rank] - amount
        if remaining:
            run["materials"][rank] = remaining
        else:
            del run["materials"][rank]
