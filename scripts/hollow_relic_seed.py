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
    def buff(name, definition, description):
        return save("hollow_buff", name=f"{prefix} {name}", effect=definition, description=description, default_duration=-1)

    def relic(name, category, rank, definition, description, flavor=""):
        return save("relic", name=f"{prefix} {name}", category=category, rank=rank,
                    buff_id=buff(name, definition, description), flavor=flavor)

    descriptions = (
        "出血を付与するとき、付与量＋1。", "ラウンド開始時、自分の出血を2減らす。",
        "出血5以上の相手への攻撃スキルの最終威力＋1。", "斬撃スキルの的中時、相手に出血1。",
        "一方攻撃時、相手に出血2。", "的中時、相手の出血が10以上なら自分のHPを2回復。",
        "マッチ勝利時、相手に出血3。", "出血10以上の相手への与ダメージ＋10%。",
        "戦闘突入時、相手全員に出血2。", "ラウンド終了時、出血している相手がいればFP＋1。",
        "マッチ敗北時、自分の出血と同じ量を相手に付与。", "的中時、相手に出血氾濫。1ラウンドに1回。",
        "自分が出血しているとき、攻撃スキルの最終威力＋2。", "ラウンド終了時、出血している相手1人につき蓄力2。",
        "的中時、相手の出血が15以上なら出血遷延を付与。", "ラウンド開始時、相手全員に出血2。",
        "出血している相手を戦闘不能にしたとき、出血している残りの敵に出血3、味方のHPを5回復。",
        "相手の出血5ごとに攻撃スキルの最終威力＋1（最大＋4）。的中すると相手の出血を半分にする。",
        "ラウンド終了時、相手全員に出血氾濫。自分に出血3。",
        "出血している相手からの被ダメージ−20%。ラウンド開始時、自分の出血を取り除く。",
    )
    flavor = {"錆びた皮剥ぎ": "刃こぼれした皮剥ぎ。柄に刻まれた名前は錆で読めない。",
              "紅涙の処刑刀": "処刑人が最後に振るった刀。刃に染みた血は、いつまでも乾かずに滴り続ける。"}
    keys = {name: relic(name, "出血", rank, definition, desc, flavor.get(name, ""))
            for (name, rank, definition), desc in zip(BLEED_RELICS, descriptions, strict=True)}
    for category in categories:
        if category != "出血":
            for rank in range(1, 6):
                relic(f"{category}の欠片 {rank}", category, rank, power("FIXED", rank, condition=attack()),
                      f"攻撃スキルの最終威力＋{rank}。")
    for threshold, name, multiplier in ((3, "発熱", 1.05), (8, "獣性の異常発達", 1.10), (14, "錯乱", 1.15)):
        save("hollow_load_stage", name=f"{prefix} {name}", threshold=threshold,
             buff_id=buff(name, {"incoming_damage_multiplier": multiplier},
                          f"被ダメージ＋{round((multiplier - 1) * 100)}%。"))
    result = relic("血脈の指輪", "出身強化", 3, effect(state("BATTLE_START", 3, stat="FP", target="self")),
                   "戦闘突入時、自分のFP＋3。", "二つの遺物が溶け合ってできた指輪。")
    save("hollow_recipe", name=f"{prefix} 血脈の指輪", result_id=result,
         material_ids=[keys["血に濡れた手袋"], keys["赤錆の釣針"]])
    return result
