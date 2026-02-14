from pathlib import Path
from types import SimpleNamespace
import importlib.util


def _mods():
    from manager.battle import common_manager as battle_common
    from manager.battle import core as battle_core
    return battle_common, battle_core


def _load_battle_common_routes_module():
    root = Path(__file__).resolve().parents[1]
    route_path = root / "events" / "battle" / "common_routes.py"
    spec = importlib.util.spec_from_file_location("battle_common_routes_for_test", route_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _make_actor(actor_id, team, placed=True):
    return {
        "id": actor_id,
        "name": actor_id,
        "type": team,
        "hp": 100,
        "maxHp": 100,
        "mp": 50,
        "maxMp": 50,
        "x": 0 if placed else -1,
        "y": 0 if placed else -1,
        "is_escaped": False,
        "special_buffs": [],
        "states": [],
        "params": [],
    }


def _base_state(characters):
    return {
        "round": 1,
        "characters": characters,
        "timeline": [],
        "battle_state": {
            "battle_id": "battle_test",
            "round": 1,
            "phase": "select",
            "slots": {},
            "timeline": [],
            "tiebreak": [],
            "intents": {},
            "redirects": [],
            "resolve": {
                "mass_queue": [],
                "single_queue": [],
                "resolved_slots": [],
                "trace": [],
            },
        },
    }


def _add_slot(state, slot_id, actor_id, team, initiative, index_in_actor=0):
    bs = state["battle_state"]
    bs["slots"][slot_id] = {
        "slot_id": slot_id,
        "actor_id": actor_id,
        "team": team,
        "index_in_actor": index_in_actor,
        "initiative": initiative,
        "disabled": False,
        "locked_target": False,
    }
    bs["timeline"].append(slot_id)


def _set_intent(
    state,
    slot_id,
    actor_id,
    skill_id,
    target_type,
    target_slot_id=None,
    committed=True,
    instant=False,
    mass_type=None,
    no_redirect=False,
):
    state["battle_state"]["intents"][slot_id] = {
        "slot_id": slot_id,
        "actor_id": actor_id,
        "skill_id": skill_id,
        "target": {"type": target_type, "slot_id": target_slot_id},
        "tags": {
            "instant": instant,
            "mass_type": mass_type,
            "no_redirect": no_redirect,
        },
        "committed": committed,
        "committed_at": 1,
    }


def _patch_room_and_socket(monkeypatch, state):
    battle_common, battle_core = _mods()
    emit_calls = []

    def _emit(event, payload=None, to=None):
        emit_calls.append((event, payload, to))

    monkeypatch.setattr(battle_core, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_core, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_core, "socketio", SimpleNamespace(emit=_emit))
    monkeypatch.setattr(battle_common, "socketio", SimpleNamespace(emit=_emit))
    return emit_calls


def test_case1_mass_processed_before_single(monkeypatch):
    _, battle_core = _mods()
    state = _base_state(
        [_make_actor("A1", "ally"), _make_actor("A2", "ally"), _make_actor("B1", "enemy"), _make_actor("B2", "enemy")]
    )
    _add_slot(state, "a1_mass", "A1", "ally", 10, 0)
    _add_slot(state, "a2_single", "A2", "ally", 8, 0)
    _add_slot(state, "b1_def", "B1", "enemy", 6, 0)
    _add_slot(state, "b2_tar", "B2", "enemy", 5, 0)
    _set_intent(state, "a1_mass", "A1", "m1", "mass_summation", None, mass_type="summation")
    _set_intent(state, "a2_single", "A2", "s1", "single_slot", "b2_tar")
    _set_intent(state, "b1_def", "B1", "d1", "single_slot", "a1_mass")
    _set_intent(state, "b2_tar", "B2", "d2", "none", None, committed=False)
    state["battle_state"]["phase"] = "resolve_mass"

    _patch_room_and_socket(monkeypatch, state)
    monkeypatch.setattr(battle_core, "_roll_power_for_slot", lambda _bs, _sid: 10)
    battle_core.run_select_resolve_auto("room_t", "battle_test")

    trace = state["battle_state"]["resolve"]["trace"]
    assert trace
    assert trace[0]["kind"].startswith("mass_")
    assert any(t["kind"] in {"clash", "one_sided", "fizzle"} for t in trace[1:])


def test_case2_redirect_overwrite_by_higher_initiative():
    battle_routes = _load_battle_common_routes_module()
    state = _base_state([])
    slots = state["battle_state"]["slots"]
    intents = state["battle_state"]["intents"]
    slots["A"] = {"slot_id": "A", "actor_id": "A1", "initiative": 9, "locked_target": False}
    slots["B"] = {"slot_id": "B", "actor_id": "B1", "initiative": 3, "locked_target": False}
    slots["C"] = {"slot_id": "C", "actor_id": "C1", "initiative": 10, "locked_target": False}
    intents["A"] = {
        "slot_id": "A",
        "actor_id": "A1",
        "skill_id": "atk_a",
        "target": {"type": "single_slot", "slot_id": "B"},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": True,
        "committed_at": 1,
    }
    intents["B"] = {
        "slot_id": "B",
        "actor_id": "B1",
        "skill_id": "atk_b",
        "target": {"type": "single_slot", "slot_id": "A"},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": True,
        "committed_at": 1,
    }
    intents["C"] = {
        "slot_id": "C",
        "actor_id": "C1",
        "skill_id": "atk_c",
        "target": {"type": "single_slot", "slot_id": "B"},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": True,
        "committed_at": 1,
    }

    battle_routes._try_apply_redirect("room_t", "battle_test", state["battle_state"], "A")
    assert state["battle_state"]["intents"]["B"]["target"]["slot_id"] == "A"
    assert state["battle_state"]["slots"]["B"]["locked_target"] is True

    battle_routes._try_apply_redirect("room_t", "battle_test", state["battle_state"], "C")
    assert state["battle_state"]["intents"]["B"]["target"]["slot_id"] == "C"
    assert state["battle_state"]["slots"]["B"]["locked_target"] is True


def test_case3_no_redirect_unlocks_target():
    battle_routes = _load_battle_common_routes_module()
    state = _base_state([])
    bs = state["battle_state"]
    bs["slots"]["B"] = {
        "slot_id": "B",
        "actor_id": "B1",
        "initiative": 3,
        "locked_target": True,
        "locked_by_slot": "A",
        "locked_by_initiative": 9,
    }
    bs["intents"]["B"] = {
        "slot_id": "B",
        "actor_id": "B1",
        "skill_id": "evade_no_redirect",
        "target": {"type": "single_slot", "slot_id": "A"},
        "tags": {"instant": False, "mass_type": None, "no_redirect": True},
        "committed": True,
        "committed_at": 1,
    }

    battle_routes._cancel_redirect_by_no_redirect("room_t", "battle_test", bs, "B", reset_target=True)

    assert bs["slots"]["B"]["locked_target"] is False
    assert bs["intents"]["B"]["target"]["type"] == "none"
    assert bs["intents"]["B"]["target"]["slot_id"] is None


def test_case4_mass_summation_uses_one_slot_per_actor(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    _add_slot(state, "S", "A1", "ally", 10, 0)
    _add_slot(state, "B_low", "B1", "enemy", 4, 0)
    _add_slot(state, "B_high", "B1", "enemy", 7, 1)
    _set_intent(state, "S", "A1", "m_sum", "mass_summation", None, mass_type="summation")
    _set_intent(state, "B_low", "B1", "d_low", "single_slot", "S")
    _set_intent(state, "B_high", "B1", "d_high", "single_slot", "S")
    state["battle_state"]["phase"] = "resolve_mass"

    _patch_room_and_socket(monkeypatch, state)
    monkeypatch.setattr(battle_core, "_roll_power_for_slot", lambda _bs, sid: {"S": 30, "B_low": 10, "B_high": 15}.get(sid, 1))
    battle_core.run_select_resolve_auto("room_t", "battle_test")

    trace = [t for t in state["battle_state"]["resolve"]["trace"] if t["kind"] == "mass_summation"]
    assert trace
    rolls = trace[0]["rolls"]
    assert len(rolls["defender_powers"]) == 1
    assert "B_high" in rolls["defender_powers"]


def test_case5_single_target_unplaced_becomes_fizzle(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy", placed=False)])
    _add_slot(state, "A_slot", "A1", "ally", 9, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 5, 0)
    _set_intent(state, "A_slot", "A1", "atk", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "dummy", "none", None, committed=False)
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)
    battle_core.run_select_resolve_auto("room_t", "battle_test")

    trace = state["battle_state"]["resolve"]["trace"]
    assert any(t["kind"] == "fizzle" and t.get("notes") == "target_unplaced" for t in trace)


def test_case6_evade_insert_promotes_one_sided_to_clash(monkeypatch):
    battle_common, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    _add_slot(state, "A_atk", "A1", "ally", 10, 0)
    _add_slot(state, "B_main", "B1", "enemy", 4, 0)
    _add_slot(state, "B_evade", "B1", "enemy", 7, 1)
    _set_intent(state, "A_atk", "A1", "atk", "single_slot", "B_main")
    _set_intent(state, "B_main", "B1", "counter", "none", None)
    _set_intent(state, "B_evade", "B1", "ev_skill", "single_slot", "A_atk")
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)
    battle_common.all_skill_data["ev_skill"] = {"分類": "回避", "tags": ["回避"]}
    monkeypatch.setattr(
        battle_common,
        "is_dodge_lock_active",
        lambda _state, actor_id: actor_id == "B1",
    )
    monkeypatch.setattr(battle_common, "get_dodge_lock_skill_id", lambda _state, _actor_id: None)

    battle_core.run_select_resolve_auto("room_t", "battle_test")
    trace = state["battle_state"]["resolve"]["trace"]

    insert_trace = next((t for t in trace if t["kind"] == "evade_insert" and t["attacker_slot"] == "A_atk"), None)
    clash_trace = next((t for t in trace if t["kind"] == "clash" and t["attacker_slot"] == "A_atk"), None)
    assert insert_trace is not None
    assert insert_trace["defender_slot"] == "B_evade"
    assert clash_trace is not None
    assert clash_trace["defender_slot"] == "B_evade"


def test_case7_clash_pair_is_resolved_once(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 9, 0)
    _set_intent(state, "A_slot", "A1", "atk_a", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "atk_b", "single_slot", "A_slot")
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)
    battle_core.run_select_resolve_auto("room_t", "battle_test")

    trace = state["battle_state"]["resolve"]["trace"]
    clash_traces = [t for t in trace if t["kind"] == "clash"]
    assert len(clash_traces) == 1

    resolved_slots = state["battle_state"]["resolve"]["resolved_slots"]
    assert resolved_slots.count("A_slot") == 1
    assert resolved_slots.count("B_slot") == 1


def test_case8_duplicate_single_queue_slot_is_skipped(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 8, 0)
    # Inject duplicate slot entry in timeline to emulate malformed/duplicated queue input.
    state["battle_state"]["timeline"] = ["A_slot", "A_slot", "B_slot"]
    _set_intent(state, "A_slot", "A1", "atk", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "idle", "none", None, committed=False)
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)
    battle_core.run_select_resolve_auto("room_t", "battle_test")

    trace = state["battle_state"]["resolve"]["trace"]
    a_slot_resolves = [t for t in trace if t.get("attacker_slot") == "A_slot" and t["kind"] in {"one_sided", "clash", "fizzle"}]
    assert len(a_slot_resolves) == 1

    resolved_slots = state["battle_state"]["resolve"]["resolved_slots"]
    assert resolved_slots.count("A_slot") == 1
