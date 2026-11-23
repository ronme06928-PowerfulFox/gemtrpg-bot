from copy import deepcopy
import json

import pytest

from manager.battle import hidden_passives
from manager.room_manager import build_participant_state
from tests.test_encyclopedia import app, client  # noqa: F401


PASSIVE = "Pa-9876"


def character():
    return {"id": "boss", "hp": 50, "maxHp": 100, "SPassive": [],
            "hidden_passives": [{"passive_id": PASSIVE,
                                 "reveal_when": {"hp_percent_lte": 50, "round_gte": 2}}],
            "flags": {"behavior_profile": {"loops": {"second": {"reveal_passive_ids": [PASSIVE]}}}}}


def test_reveal_checks_both_conditions_and_only_applies_once(monkeypatch):
    char = character()
    rebuilt, encounters = [], []
    monkeypatch.setattr(hidden_passives, "apply_passive_effect_buffs", lambda target: rebuilt.append(target))
    monkeypatch.setattr(hidden_passives, "record", lambda room, entries: encounters.extend(entries))
    hidden_passives.reveal_by_conditions("room", char, 1)
    assert char["SPassive"] == []
    char["hp"] = 51
    hidden_passives.reveal_by_conditions("room", char, 2)
    assert char["SPassive"] == []
    char["hp"] = 50
    hidden_passives.reveal_by_conditions("room", char, 2)
    assert char["SPassive"] == [PASSIVE]
    assert char["hidden_passives"] == []
    assert char["passive_revealed_round"] == 2
    assert char["passive_revealed_ids"] == [PASSIVE]
    assert not hidden_passives.reveal_passive("room", char, PASSIVE, 2)
    assert rebuilt == [char]
    assert encounters == [("passive", PASSIVE)]


def test_participant_state_contains_only_the_count():
    char = character()
    state = {"characters": [char], "logs": []}
    before = deepcopy(state)
    public = build_participant_state(state)
    assert public["characters"][0]["hidden_passive_count"] == 1
    assert PASSIVE not in json.dumps(public)
    assert "hp_percent_lte" not in json.dumps(public)
    assert build_participant_state(state, include_hidden_passives=True)["characters"][0] == char
    assert state == before


def test_state_broadcast_sends_private_data_only_to_normal_room_gm(app, monkeypatch):
    from extensions import db
    from manager import room_manager
    from models import Room, RoomMember

    room = Room(name="reveal-room", data={})
    db.session.add(room)
    db.session.flush()
    db.session.add_all([RoomMember(room_id=room.id, user_id="reader", role="player"),
                        RoomMember(room_id=room.id, user_id="author", role="gm")])
    db.session.commit()
    state = {"characters": [character()]}
    for sid, user in [("player-sid", "reader"), ("gm-sid", "author")]:
        monkeypatch.setitem(room_manager.user_sids, sid, {"user_id": user, "room": room.name})
    delivered = {}
    monkeypatch.setattr(room_manager, "_safe_emit", lambda _event, payload, to: delivered.update({to: payload}))
    room_manager.broadcast_participant_state(room.name, state)
    assert PASSIVE not in json.dumps(delivered["player-sid"])
    assert delivered["gm-sid"]["characters"][0]["hidden_passives"][0]["passive_id"] == PASSIVE


@pytest.mark.parametrize("condition", [{}, {"round_gte": True}, {"hp_percent_lte": 101}, {"unexpected": 2}])
def test_invalid_reveal_condition(condition):
    assert hidden_passives.validate_hidden_passives([{"passive_id": PASSIVE, "reveal_when": condition}], [])


def test_loop_transition_reveals_before_action_plan(monkeypatch, caplog):
    from manager.battle.pve_intent_planner import prepare_pve_behavior_round_plan

    char = character()
    char.update(type="enemy", x=4, y=4)
    char["flags"]["behavior_profile"] = {
        "enabled": True, "slot_generation_mode": "step_actions", "initial_loop_id": "first",
        "loops": {
            "first": {"transitions": [{"to_loop_id": "second"}]},
            "second": {"reveal_passive_ids": [PASSIVE], "steps": [{"actions": ["E-01"]}]},
        },
    }
    monkeypatch.setattr(hidden_passives, "record", lambda *_: None)
    state = {"characters": [char], "round": 1, "battle_mode": "pve"}
    plan = prepare_pve_behavior_round_plan(state, {"round": 1}, 1, room="room")
    assert plan["actors"]["boss"]["loop_id"] == "second"
    assert char["SPassive"] == [PASSIVE]
    assert PASSIVE not in caplog.text


def test_skill_effect_rebuilds_passive_without_triggering_battle_start(monkeypatch):
    from manager.game_logic import process_skill_effects, get_status_value
    from manager.passives.loader import passive_loader
    from manager.battle.resolve_effect_runtime import (
        _apply_effect_changes_like_duel, _diff_snapshot, _snapshot_for_outcome,
    )
    from manager.utils import apply_passive_effect_buffs

    char = character()
    char["params"] = [{"label": "敏捷", "value": 6}]
    monkeypatch.setattr(passive_loader, "load_passives", lambda: {
        PASSIVE: {"name": "秘匿効果", "effect": {"stat_mods": {"敏捷": 6},
                    "incoming_damage_multiplier": 0.5,
                    "battle_start_effect": [{"type": "APPLY_STATE", "stat": "HP", "value": 10}]}}
    })
    assert get_status_value(char, "敏捷") == 6
    before = _snapshot_for_outcome(char)
    _, logs, changes = process_skill_effects(
        [{"type": "REVEAL_PASSIVE", "timing": "PRE_MATCH", "target": "self", "passive_id": PASSIVE}],
        "PRE_MATCH", char, char, None,
    )
    assert not logs
    assert len(changes) == 1
    state = {"round": 2, "characters": [char]}
    _apply_effect_changes_like_duel(None, state, changes, char, char, 0, [])
    already_active = {"params": deepcopy(char["params"]), "SPassive": [PASSIVE]}
    apply_passive_effect_buffs(already_active)
    assert get_status_value(char, "敏捷") == get_status_value(already_active, "敏捷") == 12
    assert char["special_buffs"] == already_active["special_buffs"]
    assert not _diff_snapshot(before, _snapshot_for_outcome(char))["statuses"]
    assert char["hp"] == 50


def test_unit_and_passive_apis_do_not_disclose_hidden_data(app, monkeypatch):
    from datetime import datetime, timezone
    from extensions import db
    from models import CatalogEncounter, CatalogEntry
    from manager.passives.loader import passive_loader

    secret = "未公開の仕掛け"
    unit = {"name": "見本", "hp": 100, "marks": ["known"], "hidden_passives": character()["hidden_passives"],
            "patterns": [{"id": "BP-1", "profile": character()["flags"]["behavior_profile"]}],
            "default_pattern_id": "BP-1"}
    db.session.add(CatalogEntry(kind="unit", entry_id="U-900", payload=unit, visibility="public"))
    db.session.add(CatalogEntry(kind="passive", entry_id=PASSIVE, payload={"name": secret}))
    db.session.commit()
    monkeypatch.setattr(passive_loader, "load_passives", lambda: {PASSIVE: {"name": secret}})
    player = client(app, "reader")
    for response in (
        player.get("/api/encyclopedia"), player.get("/api/units/unit/U-900"),
        player.get("/api/get_passive_data"), player.get("/api/catalog/passive"),
        player.post("/api/drill/character", json={"source": "unit", "id": "U-900", "side": "enemy"}),
    ):
        assert response.status_code == 200, response.json
        content = json.dumps(response.json, ensure_ascii=False)
        assert PASSIVE not in content and secret not in content and "hp_percent_lte" not in content
    author_data = client(app, "author").get("/api/get_passive_data")
    assert author_data.json[PASSIVE]["name"] == secret
    assert author_data.cache_control.no_store
    db.session.add(CatalogEncounter(user_id="reader", kind="passive", entry_id=PASSIVE,
                                    first_seen_at=datetime.now(timezone.utc), room_name="room"))
    db.session.commit()
    assert player.get("/api/get_passive_data").json[PASSIVE]["name"] == secret


def test_sample_boss_changes_form_in_simulator(monkeypatch):
    from pathlib import Path
    from extensions import all_skill_data
    from manager.cache_paths import SKILLS_CACHE_FILE, load_json_cache
    from manager.passives.loader import passive_loader
    from manager.sim.battle_runner import run_battle
    from manager.sim.preset_loader import empty_room_state_for_presets
    from manager.units.characters import build_character

    path = Path(__file__).resolve().parents[1] / "data/examples/pr67_hidden_passive_boss.json"
    example = json.loads(path.read_text(encoding="utf-8"))
    passive = example["passive"]
    monkeypatch.setattr(passive_loader, "load_passives", lambda: {passive["id"]: passive["payload"]})
    cache = load_json_cache(SKILLS_CACHE_FILE)
    masters = {key: cache[key] for key in ("Ps-00", "E-01")}
    for key, entry in masters.items():
        monkeypatch.setitem(all_skill_data, key, entry)
    state = empty_room_state_for_presets()
    boss = build_character(example["unit"], "enemy", 1, masters=masters)
    hero = build_character({"name": "冒険者", "hp": 80, "mp": 20, "skills": [{"id": "Ps-00"}]},
                           "ally", 1, masters=masters)
    boss.update(x=7, y=7)
    hero.update(x=9, y=7)
    state["characters"] = [boss, hero]

    def cross_threshold(current_state, battle_state):
        if current_state["round"] == 1:
            assert boss["SPassive"] == []
            boss["hp"] = 40
        else:
            assert boss["SPassive"] == [passive["id"]]
            assert boss["special_buffs"][0]["incoming_damage_multiplier"] == .75

    report = run_battle(state, max_rounds=2, intent_provider=cross_threshold, copy_state=False,
                        roll_mode="median", auto_ally_intents=True)
    assert report.rounds == 2
    assert [row.committed_intents for row in report.rounds_detail] == [2, 2]
    assert boss["hidden_passives"] == []
