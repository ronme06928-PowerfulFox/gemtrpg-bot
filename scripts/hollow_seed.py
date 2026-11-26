"""Seed a DB copy with the smallest Hollow data that plays 1F-20F.

Usage:
    python scripts/hollow_seed.py --db _local/agent_db/gemtrpg.db
    python app.py --db _local/agent_db/gemtrpg.db

Running it again updates the same entries (matched by name, tier or floor).
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
}
TIERS = ((1, 1.0, 1.0), (2, 1.3, 1.2))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite file to seed (a copy, not instance/gemtrpg.db)")
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


def seed():
    from manager.units import repository

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

    stage = {"name": f"{PREFIX} 坑道の奥", "enemy_formation_id": formations["boss"]}
    stage_id = upsert("stage", stage, by_name(stage))

    for number, hp, attack in TIERS:
        upsert("tier", {
            "name": f"{PREFIX} T{number}", "tier": number, "hp_multiplier": hp, "attack_multiplier": attack,
            "event_weights": {"normal": 3, "elite": 1},
            "encounters": {"normal": [{"formation_id": formations["normal_1"], "weight": 2},
                                      {"formation_id": formations["normal_2"], "weight": 1}],
                           "elite": [{"formation_id": formations["elite"], "weight": 1}]},
        }, lambda other, number=number: other.get("tier") == number)
        floor = number * 10
        upsert("fixed_floor", {
            "name": f"{PREFIX} {floor}F 坑道の主", "floor": floor, "type": "boss",
            "formation_id": formations["boss"], "stage_id": stage_id,
        }, lambda other, floor=floor: other.get("floor") == floor and other.get("type") == "boss")


def main():
    args = parse_args()
    db_path = Path(args.db).resolve()
    if db_path == (ROOT / "instance/gemtrpg.db").resolve():
        sys.exit("instance/gemtrpg.db は使いません。写しを --db で指定してください。")
    app = open_app(db_path)
    with app.app_context():
        seed()
    print(f"done: {db_path}")


if __name__ == "__main__":
    main()
