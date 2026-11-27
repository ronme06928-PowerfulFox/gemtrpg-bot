"""Playable relic definitions for the disposable Hollow seed."""


def condition(param, value, *, source="target", operator="GTE"):
    return {"source": source, "param": param, "operator": operator, "value": value}


def state(timing, value, *, stat="出血", target="target", **fields):
    return {"timing": timing, "type": "APPLY_STATE", "target": target,
            "state_name": stat, "value": value, **fields}


def effect(*rows):
    return {"effects": list(rows)}


def power(operation, value, **fields):
    return {"power_bonus": [{"operation": operation, "apply_to": "final", "value": value, **fields}]}


def attack():
    return condition("tags", "攻撃", source="skill", operator="CONTAINS")


BLEEDING = condition("出血", 1)
KILLED_WHILE_BLEEDING = condition("出血", 1, source="trigger_target")
BLEEDING_ENEMIES = {"team": "enemy", "alive": True, "condition": BLEEDING}


def bleed_flood(timing, target):
    return {"timing": timing, "target": target, "type": "CUSTOM_EFFECT", "value": "出血氾濫"}


def multiply_bleed(timing, value, target):
    return {"timing": timing, "target": target, "type": "MULTIPLY_STATE", "state_name": "出血", "value": value}


BLEED_RELICS = (
    ("錆びた皮剥ぎ", 1, {"state_bonus": [{"stat": "出血", "value": 1}]}),
    ("止血帯の切れ端", 1, effect(state("START_ROUND", -2, target="self"))),
    ("血に濡れた手袋", 1, power("FIXED_IF_EXISTS", 1, source="target", param="出血", threshold=5, condition=attack())),
    ("獣の爪飾り", 1, effect(state("HIT", 1, condition=condition("属性", "斬撃", source="skill", operator="EQUALS")))),
    ("赤錆の釣針", 1, effect(state("UNOPPOSED", 2))),
    ("血吸いの鉈", 2, effect(state("HIT", 2, stat="HP", target="self",
                             condition=condition("出血", 10, source="trigger_target")))),
    ("裂け目の縫い針", 2, effect(state("WIN", 3))),
    ("赤い道標", 2, {"outgoing_damage_multiplier": 1.1, "condition": condition("出血", 10)}),
    ("狩人の結び目", 2, {"battle_start_effect": [state("BATTLE_START", 2, target="ALL_ENEMIES")]}),
    ("滴る杯", 2, effect(state("END_ROUND", 1, stat="FP", target="self", if_any_character=BLEEDING_ENEMIES))),
    ("紅の天秤", 3, effect({"timing": "LOSE", "type": "APPLY_STATE_PER_N", "target": "target",
                       "state_name": "出血", "source": "self", "source_param": "出血", "per_N": 1, "value": 1})),
    ("血錆の鉤", 3, effect({**bleed_flood("HIT", "target"), "once_per_round": True})),
    ("乾かない包帯", 3, power("FIXED_IF_EXISTS", 2, source="self", param="出血", threshold=1, condition=attack())),
    ("群れ狩りの角笛", 3, effect({"timing": "END_ROUND", "type": "APPLY_BUFF_FROM_CHARACTER_COUNT",
                        "target": "self", "buff_id": "Bu-30", "value_per_character": 2, "apply_to": "stack",
                        "lasting": -1, "character_filter": BLEEDING_ENEMIES})),
    ("血の契約書", 4, effect({"timing": "HIT", "type": "APPLY_BUFF", "target": "target", "buff_id": "Bu-08",
                       "lasting": -1, "count": 1, "condition": condition("出血", 15)})),
    ("赤き流星", 4, effect(state("START_ROUND", 2, target="ALL_ENEMIES"))),
    ("血河の舟", 4, effect(state("ON_KILL", 3, target="FILTERED_CHARACTERS",
                           character_filter=BLEEDING_ENEMIES, condition=KILLED_WHILE_BLEEDING),
                       state("ON_KILL", 5, stat="HP", target="ALL_ALLIES", condition=KILLED_WHILE_BLEEDING))),
    ("紅涙の処刑刀", 5, {**power("PER_N_BONUS", 1, source="target", param="出血", per_N=5,
                           max_bonus=4, condition=attack()), **effect(multiply_bleed("HIT", 0.5, "target"))}),
    ("血の雨", 5, effect(bleed_flood("END_ROUND", "ALL_ENEMIES"), state("END_ROUND", 3, target="self"))),
    ("赤き王冠", 5, {"incoming_damage_multiplier": 0.8, "condition": BLEEDING,
                  **effect(multiply_bleed("START_ROUND", 0, "self"))}),
)


def seed_relics(save, categories, prefix):
    def buff(name, definition):
        return save("hollow_buff", name=f"{prefix} {name}", effect=definition, default_duration=-1)

    def relic(name, category, rank, definition):
        return save("relic", name=f"{prefix} {name}", category=category, rank=rank, buff_id=buff(name, definition))

    keys = {name: relic(name, "出血", rank, definition) for name, rank, definition in BLEED_RELICS}
    for category in categories:
        if category != "出血":
            for rank in range(1, 6):
                relic(f"{category}の欠片 {rank}", category, rank, power("FIXED", rank, condition=attack()))
    for threshold, name, multiplier in ((3, "発熱", 1.05), (8, "獣性の異常発達", 1.10), (14, "錯乱", 1.15)):
        save("hollow_load_stage", name=f"{prefix} {name}", threshold=threshold,
             buff_id=buff(name, {"incoming_damage_multiplier": multiplier}))
    result = relic("血脈の指輪", "出身強化", 3, effect(state("BATTLE_START", 3, stat="FP", target="self")))
    save("hollow_recipe", name=f"{prefix} 血脈の指輪", result_id=result,
         material_ids=[keys["血に濡れた手袋"], keys["赤錆の釣針"]])
