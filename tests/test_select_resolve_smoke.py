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


def test_case7b_mutual_clash_is_preserved_under_third_party_contention(monkeypatch):
    _, battle_core = _mods()
    state = _base_state(
        [
            _make_actor("A1", "ally"),
            _make_actor("B1", "enemy"),
            _make_actor("A2", "ally"),
            _make_actor("B2", "enemy"),
        ]
    )
    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 9, 0)
    _add_slot(state, "C_slot", "A2", "ally", 8, 0)
    _add_slot(state, "D_slot", "B2", "enemy", 7, 0)

    # A <-> B is mutual clash. C also targets B (contention). D targets C.
    _set_intent(state, "A_slot", "A1", "atk_a", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "atk_b", "single_slot", "A_slot")
    _set_intent(state, "C_slot", "A2", "atk_c", "single_slot", "B_slot")
    _set_intent(state, "D_slot", "B2", "atk_d", "single_slot", "C_slot")
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)
    battle_core.run_select_resolve_auto("room_t", "battle_test")

    trace = [t for t in state["battle_state"]["resolve"]["trace"] if t["kind"] in {"clash", "one_sided", "fizzle"}]
    clash_traces = [t for t in trace if t["kind"] == "clash"]
    one_sided_traces = [t for t in trace if t["kind"] == "one_sided"]
    fizzle_traces = [t for t in trace if t["kind"] == "fizzle"]

    assert len(clash_traces) == 1
    assert clash_traces[0]["attacker_slot"] == "A_slot"
    assert clash_traces[0]["defender_slot"] == "B_slot"
    assert len(one_sided_traces) == 2
    assert len(fizzle_traces) == 0


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


def test_case9_mass_individual_applies_and_consumes_participant(monkeypatch):
    _, battle_core = _mods()
    state = _base_state(
        [_make_actor("A1", "ally"), _make_actor("B1", "enemy"), _make_actor("B2", "enemy")]
    )
    _add_slot(state, "A_mass", "A1", "ally", 10, 0)
    _add_slot(state, "B_def", "B1", "enemy", 9, 0)
    _add_slot(state, "B_idle", "B2", "enemy", 5, 0)
    _set_intent(state, "A_mass", "A1", "m_skill", "mass_individual", None, mass_type="mass_individual")
    _set_intent(state, "B_def", "B1", "d_skill", "single_slot", "A_mass")
    _set_intent(state, "B_idle", "B2", "idle", "none", None, committed=False)
    state["battle_state"]["phase"] = "resolve_mass"

    _patch_room_and_socket(monkeypatch, state)
    old_m_skill = battle_core.all_skill_data.get("m_skill")
    battle_core.all_skill_data["m_skill"] = {"cost": [{"type": "MP", "value": 5}]}

    def _stub_clash(room=None, state=None, attacker_char=None, defender_char=None, attacker_skill_data=None, defender_skill_data=None, **kwargs):
        defender_char["hp"] = int(defender_char.get("hp", 0)) - 3
        return {
            "ok": True,
            "outcome": "attacker_win",
            "summary": {
                "damage": [{"target_id": defender_char["id"], "hp": 3, "source": "ダイスダメージ"}],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "rolls": {"power_a": 8, "power_b": 5},
            },
        }

    def _stub_one_sided(room=None, state=None, attacker_char=None, defender_char=None, attacker_skill_data=None, defender_skill_data=None, **kwargs):
        defender_char["hp"] = int(defender_char.get("hp", 0)) - 7
        return {
            "ok": True,
            "summary": {
                "damage": [{"target_id": defender_char["id"], "hp": 7, "source": "one_sided_delegate"}],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 7},
            },
        }

    monkeypatch.setattr(battle_core, "_resolve_clash_by_existing_logic", _stub_clash)
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)
    try:
        battle_core.run_select_resolve_auto("room_t", "battle_test")
    finally:
        if old_m_skill is None:
            battle_core.all_skill_data.pop("m_skill", None)
        else:
            battle_core.all_skill_data["m_skill"] = old_m_skill

    chars = {c["id"]: c for c in state["characters"]}
    assert chars["B1"]["hp"] == 97
    assert chars["B2"]["hp"] == 93
    assert chars["A1"]["mp"] == 50

    slots = state["battle_state"]["slots"]
    assert slots["A_mass"]["disabled"] is True
    assert slots["B_def"]["disabled"] is True

    mass_traces = [t for t in state["battle_state"]["resolve"]["trace"] if t["kind"] == "mass_individual"]
    assert mass_traces
    assert any(isinstance(t.get("lines"), list) and t.get("lines") for t in mass_traces)


def test_case10_mass_cost_is_consumed_once_on_resolve_start(monkeypatch):
    battle_routes = _load_battle_common_routes_module()
    room_state = {"characters": [_make_actor("A1", "ally"), _make_actor("B1", "enemy")]}
    state = _base_state(room_state["characters"])
    bs = state["battle_state"]
    _add_slot(state, "A_mass", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 6, 0)
    _set_intent(state, "A_mass", "A1", "m_start", "mass_individual", None, mass_type="mass_individual")
    _set_intent(state, "B_slot", "B1", "d1", "single_slot", "A_mass")

    monkeypatch.setattr(battle_routes, "get_room_state", lambda _room: room_state)
    old_skill = battle_routes.all_skill_data.get("m_start")
    battle_routes.all_skill_data["m_start"] = {"cost": [{"type": "MP", "value": 4}]}
    try:
        rows = battle_routes._consume_mass_costs_on_resolve_start("room_t", bs, {"A_mass", "B_slot"})
        rows2 = battle_routes._consume_mass_costs_on_resolve_start("room_t", bs, {"A_mass", "B_slot"})
    finally:
        if old_skill is None:
            battle_routes.all_skill_data.pop("m_start", None)
        else:
            battle_routes.all_skill_data["m_start"] = old_skill

    chars = {c["id"]: c for c in room_state["characters"]}
    assert chars["A1"]["mp"] == 46
    assert bs["intents"]["A_mass"]["cost_consumed_at_resolve_start"] is True
    assert rows and len(rows) == 1
    assert rows2 == []


def test_case11_extract_skill_id_from_localized_skill_data():
    _, battle_core = _mods()
    sd1 = {"スキルID": "E-10"}
    sd2 = {"skillID": "Ms-00"}
    sd3 = {"チャットパレット": "9+1d6+1d{魔法補正} 【E-10 怖いでしょう？】"}
    sd4 = {"chat_palette": "4+1d2+1d7 【Pb-00 ぶーん！】"}

    assert battle_core._extract_skill_id_from_data(sd1) == "E-10"
    assert battle_core._extract_skill_id_from_data(sd2) == "Ms-00"
    assert battle_core._extract_skill_id_from_data(sd3) == "E-10"
    assert battle_core._extract_skill_id_from_data(sd4) == "Pb-00"


def test_case12_mass_slots_are_included_in_legacy_has_acted_sync(monkeypatch):
    _, battle_core = _mods()
    actors = [
        _make_actor("A1", "ally"),
        _make_actor("A2", "ally"),
        _make_actor("B1", "enemy"),
        _make_actor("B2", "enemy"),
    ]
    for actor in actors:
        actor["hasActed"] = False

    state = _base_state(actors)
    state["timeline"] = [
        {"id": "t1", "char_id": "A1", "acted": False},
        {"id": "t2", "char_id": "A2", "acted": False},
        {"id": "t3", "char_id": "B1", "acted": False},
        {"id": "t4", "char_id": "B2", "acted": False},
    ]

    _add_slot(state, "A_mass", "A1", "ally", 10, 0)
    _add_slot(state, "A_single", "A2", "ally", 8, 0)
    _add_slot(state, "B_clash", "B1", "enemy", 7, 0)
    _add_slot(state, "B_mass_def", "B2", "enemy", 6, 0)

    _set_intent(state, "A_mass", "A1", "m_skill", "mass_individual", None, mass_type="mass_individual")
    _set_intent(state, "A_single", "A2", "s_skill", "single_slot", "B_clash")
    _set_intent(state, "B_clash", "B1", "d_skill", "single_slot", "A_single")
    _set_intent(state, "B_mass_def", "B2", "d_mass", "single_slot", "A_mass")
    state["battle_state"]["phase"] = "resolve_mass"

    _patch_room_and_socket(monkeypatch, state)

    def _stub_clash(**_kwargs):
        return {
            "ok": True,
            "outcome": "attacker_win",
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "rolls": {"power_a": 7, "power_b": 5},
            },
        }

    def _stub_one_sided(**_kwargs):
        return {
            "ok": True,
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 6},
            },
        }

    monkeypatch.setattr(battle_core, "_resolve_clash_by_existing_logic", _stub_clash)
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)

    battle_core.run_select_resolve_auto("room_t", "battle_test")

    assert state["battle_state"]["phase"] == "round_end"
    assert all(entry.get("acted", False) for entry in state["timeline"])
    assert all(actor.get("hasActed", False) for actor in actors)


def test_case13_redirect_does_not_steal_targeting_mass_slot():
    battle_routes = _load_battle_common_routes_module()
    state = _base_state([])
    slots = state["battle_state"]["slots"]
    intents = state["battle_state"]["intents"]

    slots["A_fast"] = {"slot_id": "A_fast", "actor_id": "A1", "initiative": 10, "locked_target": False}
    slots["B_mid"] = {"slot_id": "B_mid", "actor_id": "B1", "initiative": 5, "locked_target": False}
    slots["M_mass"] = {"slot_id": "M_mass", "actor_id": "M1", "initiative": 4, "locked_target": False}

    intents["M_mass"] = {
        "slot_id": "M_mass",
        "actor_id": "M1",
        "skill_id": "m_skill",
        "target": {"type": "mass_individual", "slot_id": None},
        "tags": {"instant": False, "mass_type": "mass_individual", "no_redirect": False},
        "committed": True,
        "committed_at": 1,
    }
    intents["B_mid"] = {
        "slot_id": "B_mid",
        "actor_id": "B1",
        "skill_id": "b_skill",
        "target": {"type": "single_slot", "slot_id": "M_mass"},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": True,
        "committed_at": 1,
    }
    intents["A_fast"] = {
        "slot_id": "A_fast",
        "actor_id": "A1",
        "skill_id": "a_skill",
        "target": {"type": "single_slot", "slot_id": "B_mid"},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": True,
        "committed_at": 1,
    }

    battle_routes._try_apply_redirect("room_t", "battle_test", state["battle_state"], "A_fast")

    assert state["battle_state"]["intents"]["B_mid"]["target"]["slot_id"] == "M_mass"
    assert state["battle_state"]["slots"]["B_mid"]["locked_target"] is False


def test_case14_mass_summation_attacker_win_deals_delta_to_all_enemies(monkeypatch):
    _, battle_core = _mods()
    actors = [_make_actor("A1", "ally"), _make_actor("B1", "enemy"), _make_actor("B2", "enemy")]
    state = _base_state(actors)
    _add_slot(state, "S", "A1", "ally", 10, 0)
    _add_slot(state, "B1", "B1", "enemy", 7, 0)
    _add_slot(state, "B2", "B2", "enemy", 6, 0)
    _set_intent(state, "S", "A1", "m_sum", "mass_summation", None, mass_type="mass_summation")
    _set_intent(state, "B1", "B1", "d1", "single_slot", "S")
    _set_intent(state, "B2", "B2", "d2", "single_slot", "S")
    state["battle_state"]["phase"] = "resolve_mass"

    emit_calls = _patch_room_and_socket(monkeypatch, state)
    monkeypatch.setattr(
        battle_core,
        "_roll_power_for_slot",
        lambda _bs, sid: {"S": 30, "B1": 10, "B2": 15}.get(sid, 0),
    )

    battle_core.run_select_resolve_auto("room_t", "battle_test")

    chars = {c["id"]: c for c in state["characters"]}
    assert chars["A1"]["hp"] == 100
    assert chars["B1"]["hp"] == 95
    assert chars["B2"]["hp"] == 95

    stat_events = [e for e in emit_calls if e[0] == "char_stat_updated"]
    assert len(stat_events) == 2
    trace = [t for t in state["battle_state"]["resolve"]["trace"] if t["kind"] == "mass_summation"]
    assert trace
    assert trace[0]["rolls"]["delta"] == 5
    assert trace[0]["outcome"] == "attacker_win"


def test_case15_mass_summation_defender_win_deals_delta_to_attacker(monkeypatch):
    _, battle_core = _mods()
    actors = [_make_actor("A1", "ally"), _make_actor("B1", "enemy"), _make_actor("B2", "enemy")]
    state = _base_state(actors)
    _add_slot(state, "S", "A1", "ally", 10, 0)
    _add_slot(state, "B1", "B1", "enemy", 7, 0)
    _add_slot(state, "B2", "B2", "enemy", 6, 0)
    _set_intent(state, "S", "A1", "m_sum", "mass_summation", None, mass_type="mass_summation")
    _set_intent(state, "B1", "B1", "d1", "single_slot", "S")
    _set_intent(state, "B2", "B2", "d2", "single_slot", "S")
    state["battle_state"]["phase"] = "resolve_mass"

    emit_calls = _patch_room_and_socket(monkeypatch, state)
    monkeypatch.setattr(
        battle_core,
        "_roll_power_for_slot",
        lambda _bs, sid: {"S": 12, "B1": 10, "B2": 15}.get(sid, 0),
    )

    battle_core.run_select_resolve_auto("room_t", "battle_test")

    chars = {c["id"]: c for c in state["characters"]}
    assert chars["A1"]["hp"] == 87
    assert chars["B1"]["hp"] == 100
    assert chars["B2"]["hp"] == 100

    stat_events = [e for e in emit_calls if e[0] == "char_stat_updated"]
    assert len(stat_events) == 1
    trace = [t for t in state["battle_state"]["resolve"]["trace"] if t["kind"] == "mass_summation"]
    assert trace
    assert trace[0]["rolls"]["delta"] == 13
    assert trace[0]["outcome"] == "defender_win"


def test_case16_infer_mass_summation_from_japanese_distance_key():
    battle_routes = _load_battle_common_routes_module()
    battle_routes.all_skill_data.clear()
    battle_routes.all_skill_data["E-11"] = {
        "スキルID": "E-11",
        "分類": "魔法",
        "距離": "広域-合算",
        "tags": ["攻撃", "広域"],
    }

    inferred = battle_routes._infer_mass_type_from_skill("E-11")
    assert inferred == "mass_summation"

    normalized, err = battle_routes._normalize_target_by_skill(
        "E-11",
        {"type": "single_slot", "slot_id": "any_slot"},
        allow_none=False,
    )
    assert err is None
    assert normalized == {"type": "mass_summation", "slot_id": None}


def test_case16b_infer_mass_individual_from_legacy_distance_key_without_mass_tag():
    battle_routes = _load_battle_common_routes_module()
    battle_routes.all_skill_data.clear()
    battle_routes.all_skill_data["E-10"] = {
        "スキルID": "E-10",
        "分類": "魔法",
        "距離": "広域-個別",
        "tags": ["攻撃"],
    }

    inferred = battle_routes._infer_mass_type_from_skill("E-10")
    assert inferred == "mass_individual"

    normalized, err = battle_routes._normalize_target_by_skill(
        "E-10",
        {"type": "single_slot", "slot_id": "any_slot"},
        allow_none=False,
    )
    assert err is None
    assert normalized == {"type": "mass_individual", "slot_id": None}


def test_case17_select_resolve_phase_timings_are_invoked(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    _add_slot(state, "A_slot", "A1", "ally", 8, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 6, 0)
    _set_intent(state, "A_slot", "A1", "a_skill", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "b_skill", "none", None, committed=False)
    state["battle_state"]["phase"] = "resolve_single"
    state["battle_state"]["resolve"]["single_queue"] = ["A_slot"]

    _patch_room_and_socket(monkeypatch, state)

    old_a = battle_core.all_skill_data.get("a_skill")
    battle_core.all_skill_data["a_skill"] = {
        "base_power": 5,
        "dice_power": "1d1",
        "rule_data": {
            "effects": [
                {"timing": "RESOLVE_START", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
                {"timing": "RESOLVE_STEP_END", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
                {"timing": "RESOLVE_END", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
            ]
        },
    }

    seen_timings = []

    def _stub_process_skill_effects(effects_array, timing_to_check, actor, target, target_skill_data=None, context=None, base_damage=0):
        seen_timings.append(str(timing_to_check))
        return 0, [], []

    def _stub_one_sided(**_kwargs):
        return {
            "ok": True,
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 0},
            },
        }

    monkeypatch.setattr(battle_core, "process_skill_effects", _stub_process_skill_effects)
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)
    try:
        battle_core.run_select_resolve_auto("room_t", "battle_test")
    finally:
        if old_a is None:
            battle_core.all_skill_data.pop("a_skill", None)
        else:
            battle_core.all_skill_data["a_skill"] = old_a

    assert "RESOLVE_START" in seen_timings
    assert "RESOLVE_STEP_END" in seen_timings
    assert "RESOLVE_END" in seen_timings


def test_case18_one_sided_chain_includes_pre_before_after_damage(monkeypatch):
    _, battle_core = _mods()
    attacker = _make_actor("A1", "ally")
    defender = _make_actor("B1", "enemy")
    state = _base_state([attacker, defender])

    skill_a = {
        "base_power": 5,
        "dice_power": "1d1",
        "rule_data": {
            "effects": [
                {"timing": "PRE_MATCH", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
                {"timing": "BEFORE_POWER_ROLL", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
                {"timing": "UNOPPOSED", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
                {"timing": "HIT", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
                {"timing": "AFTER_DAMAGE_APPLY", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
            ]
        },
    }
    skill_d = {
        "base_power": 3,
        "dice_power": "1d1",
        "rule_data": {"effects": [{"timing": "PRE_MATCH", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1}]},
    }

    seen_timings = []

    def _stub_process_skill_effects(effects_array, timing_to_check, actor, target, target_skill_data=None, context=None, base_damage=0):
        seen_timings.append(str(timing_to_check))
        return 0, [], []

    monkeypatch.setattr(battle_core, "process_skill_effects", _stub_process_skill_effects)
    monkeypatch.setattr(battle_core, "roll_dice", lambda _cmd: {"total": 5})
    monkeypatch.setattr(battle_core, "process_on_hit_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(battle_core, "process_on_damage_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(battle_core, "calculate_damage_multiplier", lambda *_args, **_kwargs: (1.0, []))

    def _stub_update_char_stat(_room, char, name, value, **_kwargs):
        if name == "HP":
            char["hp"] = int(value)
        elif name == "MP":
            char["mp"] = int(value)
        else:
            states = char.setdefault("states", [])
            hit = next((s for s in states if s.get("name") == name), None)
            if hit is None:
                states.append({"name": name, "value": int(value)})
            else:
                hit["value"] = int(value)

    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)

    battle_core._resolve_one_sided_by_existing_logic(
        room="room_t",
        state=state,
        attacker_char=attacker,
        defender_char=defender,
        attacker_skill_data=skill_a,
        defender_skill_data=skill_d,
    )

    assert "PRE_MATCH" in seen_timings
    assert "BEFORE_POWER_ROLL" in seen_timings
    assert "UNOPPOSED" in seen_timings
    assert "HIT" in seen_timings
    assert "AFTER_DAMAGE_APPLY" in seen_timings


def test_case19_use_skill_again_reuses_same_skill_once_without_extra_cost(monkeypatch):
    _, battle_core = _mods()
    attacker = _make_actor("A1", "ally")
    defender = _make_actor("B1", "enemy")
    attacker["states"] = [{"name": "FP", "value": 10}]
    state = _base_state([attacker, defender])

    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 8, 0)
    _set_intent(state, "A_slot", "A1", "atk_reuse", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "idle", "none", None, committed=False)
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)

    old_skill = battle_core.all_skill_data.get("atk_reuse")
    battle_core.all_skill_data["atk_reuse"] = {
        "base_power": 5,
        "dice_power": "1d1",
        "rule_data": {
            "cost": [{"type": "FP", "value": 3}],
            "effects": [
                {"timing": "HIT", "type": "USE_SKILL_AGAIN", "max_reuses": 1}
            ],
        },
    }

    monkeypatch.setattr(battle_core, "roll_dice", lambda _cmd: {"total": 5})
    monkeypatch.setattr(battle_core, "process_on_hit_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(battle_core, "process_on_damage_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(battle_core, "calculate_damage_multiplier", lambda *_args, **_kwargs: (1.0, []))
    def _stub_update_char_stat(_room, char, name, value, **_kwargs):
        if name == "HP":
            char["hp"] = int(value)
        elif name == "MP":
            char["mp"] = int(value)
        else:
            states = char.setdefault("states", [])
            hit = next((s for s in states if s.get("name") == name), None)
            if hit is None:
                states.append({"name": name, "value": int(value)})
            else:
                hit["value"] = int(value)
    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)

    try:
        battle_core.run_select_resolve_auto("room_t", "battle_test")
    finally:
        if old_skill is None:
            battle_core.all_skill_data.pop("atk_reuse", None)
        else:
            battle_core.all_skill_data["atk_reuse"] = old_skill

    one_sided = [t for t in state["battle_state"]["resolve"]["trace"] if t.get("kind") == "one_sided"]
    assert len(one_sided) == 2
    assert one_sided[0].get("defender_slot") == "B_slot"
    assert str(one_sided[1].get("attacker_slot", "")).startswith("A_slot__EX1")
    assert one_sided[1].get("defender_slot") == "B_slot"
    assert int(one_sided[0].get("cost", {}).get("fp", 0)) == 3
    assert int(one_sided[1].get("cost", {}).get("fp", 0)) == 0
    assert one_sided[1].get("display_label") == f"{one_sided[0].get('step')}-EX"


def test_case20_use_skill_again_triggers_after_clash_win(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 9, 0)
    _set_intent(state, "A_slot", "A1", "atk_reuse", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "def_skill", "single_slot", "A_slot")
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)

    old_atk = battle_core.all_skill_data.get("atk_reuse")
    old_def = battle_core.all_skill_data.get("def_skill")
    battle_core.all_skill_data["atk_reuse"] = {
        "base_power": 5,
        "dice_power": "1d1",
        "rule_data": {
            "effects": [
                {"timing": "HIT", "type": "USE_SKILL_AGAIN", "max_reuses": 1}
            ]
        },
    }
    battle_core.all_skill_data["def_skill"] = {
        "base_power": 4,
        "dice_power": "1d1",
        "rule_data": {"effects": []},
    }

    def _stub_clash(**_kwargs):
        return {
            "ok": True,
            "outcome": "attacker_win",
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "rolls": {"power_a": 12, "power_b": 8, "tie_break": None},
            },
        }

    def _stub_one_sided(**_kwargs):
        return {
            "ok": True,
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 0},
            },
        }

    def _stub_update_char_stat(_room, char, name, value, **_kwargs):
        if name == "HP":
            char["hp"] = int(value)
        elif name == "MP":
            char["mp"] = int(value)
        else:
            states = char.setdefault("states", [])
            hit = next((s for s in states if s.get("name") == name), None)
            if hit is None:
                states.append({"name": name, "value": int(value)})
            else:
                hit["value"] = int(value)

    monkeypatch.setattr(battle_core, "_resolve_clash_by_existing_logic", _stub_clash)
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)
    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)
    try:
        battle_core.run_select_resolve_auto("room_t", "battle_test")
    finally:
        if old_atk is None:
            battle_core.all_skill_data.pop("atk_reuse", None)
        else:
            battle_core.all_skill_data["atk_reuse"] = old_atk
        if old_def is None:
            battle_core.all_skill_data.pop("def_skill", None)
        else:
            battle_core.all_skill_data["def_skill"] = old_def

    trace = [t for t in state["battle_state"]["resolve"]["trace"] if t.get("kind") in {"clash", "one_sided"}]
    assert len(trace) == 2
    assert trace[0].get("kind") == "clash"
    assert trace[1].get("kind") == "one_sided"
    assert str(trace[1].get("attacker_slot", "")).startswith("A_slot__EX1")
    assert trace[1].get("display_label") == f"{trace[0].get('step')}-EX"


def test_case21_use_skill_again_survives_single_queue_rebinding(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 9, 0)
    _set_intent(state, "A_slot", "A1", "atk_reuse", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "def_skill", "single_slot", "A_slot")
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)

    old_atk = battle_core.all_skill_data.get("atk_reuse")
    old_def = battle_core.all_skill_data.get("def_skill")
    battle_core.all_skill_data["atk_reuse"] = {
        "base_power": 5,
        "dice_power": "1d1",
        "rule_data": {
            "effects": [
                {"timing": "HIT", "type": "USE_SKILL_AGAIN", "max_reuses": 1}
            ]
        },
    }
    battle_core.all_skill_data["def_skill"] = {
        "base_power": 4,
        "dice_power": "1d1",
        "rule_data": {"effects": []},
    }

    def _stub_clash(**_kwargs):
        return {
            "ok": True,
            "outcome": "attacker_win",
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "rolls": {"power_a": 12, "power_b": 8, "tie_break": None},
            },
        }

    def _stub_one_sided(**_kwargs):
        return {
            "ok": True,
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 0},
            },
        }

    def _stub_log_match_result(_lines):
        # Reproduce runtime side-effect where ensure can reassign single_queue list object.
        resolve = state["battle_state"].setdefault("resolve", {})
        queue = resolve.get("single_queue", [])
        resolve["single_queue"] = list(queue)

    monkeypatch.setattr(battle_core, "_resolve_clash_by_existing_logic", _stub_clash)
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)
    monkeypatch.setattr(battle_core, "_log_match_result", _stub_log_match_result)
    try:
        battle_core.run_select_resolve_auto("room_t", "battle_test")
    finally:
        if old_atk is None:
            battle_core.all_skill_data.pop("atk_reuse", None)
        else:
            battle_core.all_skill_data["atk_reuse"] = old_atk
        if old_def is None:
            battle_core.all_skill_data.pop("def_skill", None)
        else:
            battle_core.all_skill_data["def_skill"] = old_def

    trace = [t for t in state["battle_state"]["resolve"]["trace"] if t.get("kind") in {"clash", "one_sided"}]
    assert len(trace) == 2
    assert trace[0].get("kind") == "clash"
    assert trace[1].get("kind") == "one_sided"
    assert str(trace[1].get("attacker_slot", "")).startswith("A_slot__EX1")


def test_case22_use_skill_again_label_stays_origin_based(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 9, 0)
    _set_intent(state, "A_slot", "A1", "atk_reuse", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "def_skill", "single_slot", "A_slot")
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)

    old_atk = battle_core.all_skill_data.get("atk_reuse")
    old_def = battle_core.all_skill_data.get("def_skill")
    battle_core.all_skill_data["atk_reuse"] = {
        "base_power": 5,
        "dice_power": "1d1",
        "rule_data": {
            "effects": [
                {"timing": "HIT", "type": "USE_SKILL_AGAIN", "max_reuses": 2}
            ]
        },
    }
    battle_core.all_skill_data["def_skill"] = {
        "base_power": 4,
        "dice_power": "1d1",
        "rule_data": {"effects": []},
    }

    def _stub_clash(**_kwargs):
        return {
            "ok": True,
            "outcome": "attacker_win",
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "rolls": {"power_a": 12, "power_b": 8, "tie_break": None},
            },
        }

    def _stub_one_sided(**_kwargs):
        return {
            "ok": True,
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "reuse_requests": [{"max_reuses": 2, "consume_cost": False}],
                "rolls": {"total_damage": 0},
            },
        }

    def _stub_update_char_stat(_room, char, name, value, **_kwargs):
        if name == "HP":
            char["hp"] = int(value)
        elif name == "MP":
            char["mp"] = int(value)
        else:
            states = char.setdefault("states", [])
            hit = next((s for s in states if s.get("name") == name), None)
            if hit is None:
                states.append({"name": name, "value": int(value)})
            else:
                hit["value"] = int(value)

    monkeypatch.setattr(battle_core, "_resolve_clash_by_existing_logic", _stub_clash)
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)
    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)
    try:
        battle_core.run_select_resolve_auto("room_t", "battle_test")
    finally:
        if old_atk is None:
            battle_core.all_skill_data.pop("atk_reuse", None)
        else:
            battle_core.all_skill_data["atk_reuse"] = old_atk
        if old_def is None:
            battle_core.all_skill_data.pop("def_skill", None)
        else:
            battle_core.all_skill_data["def_skill"] = old_def

    trace = [t for t in state["battle_state"]["resolve"]["trace"] if t.get("kind") in {"clash", "one_sided"}]
    assert len(trace) == 3
    assert trace[0].get("kind") == "clash"
    assert str(trace[1].get("attacker_slot", "")).startswith("A_slot__EX1")
    assert str(trace[2].get("attacker_slot", "")).startswith("A_slot__EX2")
    assert trace[1].get("display_label") == f"{trace[0].get('step')}-EX"
    assert trace[2].get("display_label") == f"{trace[0].get('step')}-EX2"


def test_case23_use_skill_again_reuse_cost_blocks_next_reuse_when_insufficient(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    attacker = next(c for c in state["characters"] if c["id"] == "A1")
    attacker["states"] = [{"name": "FP", "value": 1}]
    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 9, 0)
    _set_intent(state, "A_slot", "A1", "atk_reuse", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "def_skill", "single_slot", "A_slot")
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)

    old_atk = battle_core.all_skill_data.get("atk_reuse")
    old_def = battle_core.all_skill_data.get("def_skill")
    battle_core.all_skill_data["atk_reuse"] = {
        "base_power": 5,
        "dice_power": "1d1",
        "rule_data": {
            "effects": [
                {
                    "timing": "HIT",
                    "type": "USE_SKILL_AGAIN",
                    "max_reuses": 2,
                    "reuse_cost": [{"type": "FP", "value": 1}],
                }
            ]
        },
    }
    battle_core.all_skill_data["def_skill"] = {
        "base_power": 4,
        "dice_power": "1d1",
        "rule_data": {"effects": []},
    }

    def _stub_clash(**_kwargs):
        return {
            "ok": True,
            "outcome": "attacker_win",
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "rolls": {"power_a": 12, "power_b": 8, "tie_break": None},
            },
        }

    def _stub_one_sided(**_kwargs):
        return {
            "ok": True,
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "reuse_requests": [
                    {
                        "max_reuses": 2,
                        "consume_cost": False,
                        "reuse_cost": [{"type": "FP", "value": 1}],
                    }
                ],
                "rolls": {"total_damage": 0},
            },
        }

    def _stub_update_char_stat(_room, char, name, value, **_kwargs):
        if name == "HP":
            char["hp"] = int(value)
        elif name == "MP":
            char["mp"] = int(value)
        else:
            states = char.setdefault("states", [])
            hit = next((s for s in states if s.get("name") == name), None)
            if hit is None:
                states.append({"name": name, "value": int(value)})
            else:
                hit["value"] = int(value)

    monkeypatch.setattr(battle_core, "_resolve_clash_by_existing_logic", _stub_clash)
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)
    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)
    try:
        battle_core.run_select_resolve_auto("room_t", "battle_test")
    finally:
        if old_atk is None:
            battle_core.all_skill_data.pop("atk_reuse", None)
        else:
            battle_core.all_skill_data["atk_reuse"] = old_atk
        if old_def is None:
            battle_core.all_skill_data.pop("def_skill", None)
        else:
            battle_core.all_skill_data["def_skill"] = old_def

    trace = [t for t in state["battle_state"]["resolve"]["trace"] if t.get("kind") in {"clash", "one_sided"}]
    assert len(trace) == 2
    assert trace[0].get("kind") == "clash"
    assert trace[1].get("kind") == "one_sided"
    assert str(trace[1].get("attacker_slot", "")).startswith("A_slot__EX1")
    fp_state = next((s for s in attacker.get("states", []) if s.get("name") == "FP"), None)
    assert int((fp_state or {}).get("value", 0)) == 0


def test_case24_step_total_does_not_carry_over_when_trace_reset(monkeypatch):
    _, battle_core = _mods()
    state = _base_state([_make_actor("A1", "ally"), _make_actor("B1", "enemy")])
    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 9, 0)
    _set_intent(state, "A_slot", "A1", "atk", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "def", "single_slot", "A_slot")
    state["battle_state"]["phase"] = "resolve_single"
    # Reproduce stale carry-over from a previous round.
    state["battle_state"].setdefault("resolve", {})["step_total"] = 29
    state["battle_state"]["resolve"]["trace"] = []

    _patch_room_and_socket(monkeypatch, state)

    old_atk = battle_core.all_skill_data.get("atk")
    old_def = battle_core.all_skill_data.get("def")
    battle_core.all_skill_data["atk"] = {
        "base_power": 5,
        "dice_power": "1d1",
        "rule_data": {"effects": []},
    }
    battle_core.all_skill_data["def"] = {
        "base_power": 4,
        "dice_power": "1d1",
        "rule_data": {"effects": []},
    }

    def _stub_clash(**_kwargs):
        return {
            "ok": True,
            "outcome": "attacker_win",
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "rolls": {"power_a": 10, "power_b": 8, "tie_break": None},
            },
        }

    def _stub_one_sided(**_kwargs):
        return {
            "ok": True,
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 0},
            },
        }

    monkeypatch.setattr(battle_core, "_resolve_clash_by_existing_logic", _stub_clash)
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)
    try:
        battle_core.run_select_resolve_auto("room_t", "battle_test")
    finally:
        if old_atk is None:
            battle_core.all_skill_data.pop("atk", None)
        else:
            battle_core.all_skill_data["atk"] = old_atk
        if old_def is None:
            battle_core.all_skill_data.pop("def", None)
        else:
            battle_core.all_skill_data["def"] = old_def

    trace = state["battle_state"]["resolve"]["trace"]
    assert len(trace) >= 1
    first_total = int((trace[0] or {}).get("step_total", 0))
    assert first_total > 0
    assert first_total < 29


def test_case25_one_sided_self_destruct_kills_attacker(monkeypatch):
    _, battle_core = _mods()
    attacker = _make_actor("A1", "ally")
    defender = _make_actor("B1", "enemy")
    state = _base_state([attacker, defender])
    _add_slot(state, "A_slot", "A1", "ally", 10, 0)
    _add_slot(state, "B_slot", "B1", "enemy", 8, 0)
    _set_intent(state, "A_slot", "A1", "sd_skill", "single_slot", "B_slot")
    _set_intent(state, "B_slot", "B1", "idle", "none", None, committed=False)
    state["battle_state"]["phase"] = "resolve_single"

    _patch_room_and_socket(monkeypatch, state)

    old_skill = battle_core.all_skill_data.get("sd_skill")
    battle_core.all_skill_data["sd_skill"] = {
        "base_power": 1,
        "dice_power": "1d1",
        "rule_data": {"tags": ["自滅"], "effects": []},
        "tags": ["攻撃", "自滅"],
    }

    def _stub_one_sided(**_kwargs):
        return {
            "ok": True,
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 0},
            },
        }

    def _stub_update_char_stat(_room, char, name, value, **_kwargs):
        if name == "HP":
            char["hp"] = int(value)
            if char["hp"] <= 0:
                char["x"] = -1
                char["y"] = -1
        elif name == "MP":
            char["mp"] = int(value)
        else:
            states = char.setdefault("states", [])
            hit = next((s for s in states if s.get("name") == name), None)
            if hit is None:
                states.append({"name": name, "value": int(value)})
            else:
                hit["value"] = int(value)

    logs = []
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)
    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)
    monkeypatch.setattr(
        battle_core,
        "broadcast_log",
        lambda _room, message, _type="system", save=True: logs.append(str(message)),
    )

    try:
        battle_core.run_select_resolve_auto("room_t", "battle_test")
    finally:
        if old_skill is None:
            battle_core.all_skill_data.pop("sd_skill", None)
        else:
            battle_core.all_skill_data["sd_skill"] = old_skill

    assert int(attacker.get("hp", 0)) == 0
    assert any("自滅" in line for line in logs)
