"""Seed a DB copy with the smallest Hollow data that plays 1F-20F.

Usage:
    python scripts/hollow_seed.py --db _local/agent_db/gemtrpg.db
    python app.py --db _local/agent_db/gemtrpg.db

Running it again updates the same entries (matched by name or tier).
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "_local/agent_db/gemtrpg.db"
PREFIX = "試遊"

# name, grade, hp, physical bonus, speed bonus, skills (the first one opens the chart)
UNITS = {
    "iron": ("鉄級の坑道ネズミ", "鉄級", 40, 2, 1, ["E-00", "E-01"]),
    "copper": ("銅級の坑道ヤモリ", "銅級", 70, 3, 2, ["E-02", "E-00"]),
    "silver": ("銀級の坑道の主", "銀級", 260, 5, 3, ["E-14", "E-02"]),
}
FORMATIONS = {
    "normal_1": ("通常 ネズミ2", [("iron", 2)]),
    "normal_2": ("通常 ネズミとヤモリ", [("iron", 1), ("copper", 1)]),
    "elite": ("精鋭 ヤモリ2", [("copper", 2)]),
    "boss": ("ボス 坑道の主", [("silver", 1), ("iron", 1)]),
    "boss_alt": ("ボス 晶殻の群れ", [("copper", 3)]),
}
TIERS = ((1, 1.0, 1.0), (2, 1.3, 1.2))
MAPS = (
    (1, "鉄の坑道", "ネズミの群れが住む坑道", "normal_1", "boss"),
    (1, "青晶洞", "ヤモリの群れが潜む洞窟", "normal_2", "boss_alt"),
    (2, "古い晶脈", "銅級の群れの先に坑道の主がいる", "normal_2", "boss"),
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite file to seed (a copy, not instance/gemtrpg.db)")
    parser.add_argument("--battle-only", action="store_true", help="omit event nodes for battle-only smoke scripts")
    return parser.parse_args()


def open_app(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["GEMTRPG_DB"] = str(db_path)
    os.environ["GEMTRPG_DISABLE_DEFAULT_APP"] = "1"
    sys.path.insert(0, str(ROOT))
    from app import create_app

    # Startup creates the schema and imports master data into an empty DB.
    return create_app(config={"SQLALCHEMY_DATABASE_URI": "sqlite:///" + db_path.as_posix()},
                      register_sockets=False)


def seed(*, battle_only=False):
    from manager.hollow.resources import DRAW_CATEGORIES
    from manager.units import repository
    from scripts.hollow_relic_seed import seed_relics

    current = repository.entries(domain="hollow")

    def upsert(kind, payload, same):
        row = next((row for (row_kind, _), row in current.items()
                    if row_kind == kind and not row["deprecated"] and same(row["payload"])), None)
        saved, warnings = repository.save(
            kind, row and row["entry_id"], {"domain": "hollow", **payload},
            base_revision=row and row["revision"])
        for path, message in warnings.items():
            print(f"  warning {kind} {path}: {message}")
        print(f"  {'updated' if row else 'created'} {saved.entry_id} {payload['name']}")
        return saved.entry_id

    def by_name(payload):
        return lambda other: other.get("name") == payload["name"]

    units = {}
    for key, (name, grade, hp, physical, speed, skills) in UNITS.items():
        payload = {
            "name": f"{PREFIX} {name}", "hp": hp, "mp": 0, "tags": [f"等級:{grade}"],
            "allow_ally": False, "allow_enemy": True,
            "params": [{"label": "物理補正", "value": physical}, {"label": "魔法補正", "value": 0},
                       {"label": "速度補正", "value": speed}],
            "skills": [{"id": skill} for skill in skills],
            "behavior": {"auto_target": True, "auto_skill": True, "show_planned": True},
            "patterns": [{"id": "basic", "name": "基本", "profile": {
                "enabled": True, "loops": {"L1": {"repeat": True, "steps": [
                    {"actions": [skill]} for skill in skills]}}}}],
            "default_pattern_id": "basic",
        }
        units[key] = upsert("unit", payload, by_name(payload))

    formations = {}
    for key, (name, members) in FORMATIONS.items():
        payload = {"name": f"{PREFIX} {name}", "type": "enemy",
                   "members": [{"unit_id": units[unit], "count": count, "pattern_id": None}
                               for unit, count in members]}
        formations[key] = upsert("formation", payload, by_name(payload))

    stages = {}
    for key, name in (("boss", "坑道の奥"), ("boss_alt", "青晶の広間")):
        stage = {"name": f"{PREFIX} {name}", "enemy_formation_id": formations[key]}
        stages[key] = upsert("stage", stage, by_name(stage))

    for number, hp, attack in TIERS:
        upsert("tier", {
            "name": f"{PREFIX} T{number}", "tier": number, "hp_multiplier": hp, "attack_multiplier": attack,
            "boss_exp": number, "boss_radiance": number,
        }, lambda other, number=number: other.get("tier") == number)

    relic = seed_relics(lambda kind, **payload: upsert(kind, payload, by_name(payload)), DRAW_CATEGORIES, PREFIX)
    tables = {} if battle_only else seed_events(upsert, by_name, relic)
    categories = ({"出血": 5, "打撃": 4, "蓄力": 3, "汎用": 2}, {"出血": 5}, {"斬撃": 4, "亀裂": 3, "凝魔": 2})
    for (number, name, description, normal, boss), weights in zip(MAPS, categories):
        payload = {
            "name": f"{PREFIX} {name}", "description": description, "tier": number,
            "event_weights": {"normal": 3, "elite": 1, **({"chest": 4, "miasma": 6} if tables else {})},
            "category_weights": weights, **tables,
            "image": "/static/images/backgrounds/暗い遺跡洞窟.webp" if name == "青晶洞" else "",
            "encounters": {"normal": [{"formation_id": formations[normal], "weight": 1}],
                           "elite": [{"formation_id": formations["elite"], "weight": 1}]},
            "boss_formation_id": formations[boss], "boss_stage_id": stages[boss],
        }
        upsert("hollow_map", payload, by_name(payload))


def seed_events(upsert, by_name, relic):
    def save(kind, name, **fields):
        payload = {"name": f"{PREFIX} {name}", **fields}
        return upsert(kind, payload, by_name(payload))

    buff = save("hollow_buff", "魔素の残響", description="次の戦闘で攻撃威力に影響する。",
                effect={"power_bonus": [{"value": 1}]})
    item = save("hollow_item", "晶脈の小瓶", usable=True, description="淡く光る晶脈の小瓶。魔素の残響を付与する。",
                effect={"type": "buff", "buff_id": buff})
    check = save("hollow_event", "記憶の泉", text="水面に遠い記憶が映る。", choices=[
        {"label": "記憶を読む", "difficulty": 6, "skill": "鑑定",
         "effect": {"kind": "relic", "id": relic},
         "failure_effect": {"kind": "buff", "id": buff, "battles": 2}, "failure_target": "all"},
        {"label": "残響に触れる", "difficulty": 10, "skill": "五感",
         "effect": {"kind": "buff", "id": buff, "battles": 1}, "target": "selected",
         "failure_effect": {"kind": "buff", "id": buff, "battles": 2}, "failure_target": "all"},
        {"label": "やり過ごす"},
    ])
    quiet = save("hollow_event", "仄光の澱み", text="光の粒が空の小瓶に集まる。", choices=[
        {"label": "小瓶に集める", "effect": {"kind": "item", "id": item}},
        {"label": "やり過ごす"},
    ])
    drops = save("drop_table", "坑道の宝箱", rows=[
        {"kind": "item", "id": item, "weight": 2}, {"kind": "relic", "id": relic, "weight": 1},
    ])
    chest = save("treasure_chest", "坑道の宝箱", text="石の箱。蓋に細い傷が走る。", drop_table_id=drops)
    for floor, name, line in ((10, "石灯の町", "石灯が旅人を照らす。"),
                              (20, "晶脈の町", "結晶の明かりの下で休む。")):
        payload = {"name": f"{PREFIX} {name}", "floor": floor, "type": "town", "text": line}
        upsert("fixed_floor", payload, lambda other, floor=floor: other.get("floor") == floor)
    return {"events": [{"event_id": key, "weight": weight} for key, weight in ((check, 3), (quiet, 1))],
            "chests": [{"chest_id": chest, "weight": 1}]}


def main():
    args = parse_args()
    db_path = Path(args.db).resolve()
    if db_path == (ROOT / "instance/gemtrpg.db").resolve():
        sys.exit("instance/gemtrpg.db は使いません。写しを --db で指定してください。")
    app = open_app(db_path)
    with app.app_context():
        seed(battle_only=args.battle_only)
    print(f"done: {db_path}")


if __name__ == "__main__":
    main()
