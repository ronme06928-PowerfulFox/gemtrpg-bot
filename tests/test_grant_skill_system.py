from manager.game_logic import process_skill_effects
from manager.granted_skills import service as granted_service
from events.battle import common_routes


def test_process_skill_effects_emits_grant_skill_change():
    actor = {"id": "A", "name": "Caster", "type": "ally", "hp": 20, "states": [], "params": []}
    target = {"id": "B", "name": "Target", "type": "enemy", "hp": 20, "states": [], "params": []}
    effects = [
        {
            "timing": "HIT",
            "type": "GRANT_SKILL",
            "target": "target",
            "skill_id": "S-Grant",
            "grant_mode": "usage_count",
            "uses": 2,
        }
    ]

    _, _, changes = process_skill_effects(
        effects,
        "HIT",
        actor,
        target,
        context={"characters": [actor, target], "room": "room_test"},
    )

    grant_changes = [c for c in changes if c[1] == "GRANT_SKILL"]
    assert len(grant_changes) == 1
    assert grant_changes[0][2] == "S-Grant"
    assert grant_changes[0][3]["grant_mode"] == "usage_count"
    assert int(grant_changes[0][3]["uses"]) == 2


def test_all_other_allies_targets_allies_except_self():
    actor = {"id": "A", "name": "Caster", "type": "ally", "hp": 20, "states": [], "params": []}
    ally = {"id": "B", "name": "Ally", "type": "ally", "hp": 20, "states": [], "params": []}
    dead_ally = {"id": "C", "name": "Dead", "type": "ally", "hp": 0, "states": [], "params": []}
    enemy = {"id": "E", "name": "Enemy", "type": "enemy", "hp": 20, "states": [], "params": []}
    effects = [
        {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "ALL_OTHER_ALLIES",
            "state_name": "FP",
            "value": 1,
        }
    ]

    _, _, changes = process_skill_effects(
        effects,
        "HIT",
        actor,
        enemy,
        context={"characters": [actor, ally, dead_ally, enemy], "room": "room_test"},
    )
    targets = [c[0]["id"] for c in changes if c[1] == "APPLY_STATE"]
    assert targets == ["B"]


def test_grant_skill_overwrite_consume_and_expire(monkeypatch):
    monkeypatch.setattr(
        granted_service,
        "all_skill_data",
        {"S-Grant": {"チャットパレット": "1d6 【S-Grant 付与スキル】"}},
    )

    state = {"round": 1, "characters": []}
    source = {"id": "src", "name": "Source"}
    target = {"id": "tgt", "name": "Target", "commands": "", "granted_skills": []}

    r1 = granted_service.apply_grant_skill_change(
        "room_t",
        state,
        source,
        target,
        {"skill_id": "S-Grant", "grant_mode": "duration_rounds", "duration": 3, "overwrite": True},
    )
    assert r1["ok"] is True
    assert "S-Grant" in target.get("commands", "")
    assert target["granted_skills"][0]["mode"] == "duration_rounds"
    assert int(target["granted_skills"][0]["remaining_rounds"]) == 3

    r2 = granted_service.apply_grant_skill_change(
        "room_t",
        state,
        source,
        target,
        {"skill_id": "S-Grant", "grant_mode": "usage_count", "uses": 2, "overwrite": True},
    )
    assert r2["ok"] is True
    assert target["granted_skills"][0]["mode"] == "usage_count"
    assert int(target["granted_skills"][0]["remaining_uses"]) == 2

    expired_1 = granted_service.consume_granted_skill_use(target, "S-Grant")
    assert expired_1 == []
    assert int(target["granted_skills"][0]["remaining_uses"]) == 1

    expired_2 = granted_service.consume_granted_skill_use(target, "S-Grant")
    assert len(expired_2) == 1
    assert target.get("granted_skills", []) == []
    assert "S-Grant" not in target.get("commands", "")


def test_grant_duration_expire_keeps_natural_command(monkeypatch):
    monkeypatch.setattr(
        granted_service,
        "all_skill_data",
        {"S-Grant": {"チャットパレット": "1d6 【S-Grant 付与スキル】"}},
    )
    state = {"round": 1, "characters": []}
    source = {"id": "src", "name": "Source"}
    target = {
        "id": "tgt",
        "name": "Target",
        "commands": "1d6 【S-Grant 元スキル】",
        "granted_skills": [],
    }
    granted_service.apply_grant_skill_change(
        "room_t",
        state,
        source,
        target,
        {"skill_id": "S-Grant", "grant_mode": "duration_rounds", "duration": 1, "overwrite": True},
    )
    state["characters"] = [target]
    expired = granted_service.process_granted_skill_round_end(state, room="room_t")
    assert len(expired) == 1
    assert target.get("granted_skills", []) == []
    assert "S-Grant" in target.get("commands", "")


def test_target_scope_default_enemy_and_ally_override(monkeypatch):
    monkeypatch.setattr(
        common_routes,
        "all_skill_data",
        {
            "S-Default": {"スキルID": "S-Default"},
            "S-AllyOnly": {"スキルID": "S-AllyOnly", "target_scope": "ally"},
            "S-Any": {"スキルID": "S-Any", "target_scope": "any"},
        },
    )
    state = {
        "slots": {
            "S1": {"slot_id": "S1", "actor_id": "A", "team": "ally"},
            "S2": {"slot_id": "S2", "actor_id": "E", "team": "enemy"},
            "S3": {"slot_id": "S3", "actor_id": "B", "team": "ally"},
        },
        "characters": [
            {"id": "A", "type": "ally"},
            {"id": "B", "type": "ally"},
            {"id": "E", "type": "enemy"},
        ],
    }

    # default scope=enemy -> ally target should be rejected
    normalized, err = common_routes._normalize_target_by_skill(
        "S-Default",
        {"type": "single_slot", "slot_id": "S3"},
        state=state,
        source_slot_id="S1",
        allow_none=False,
    )
    assert normalized is None
    assert err

    # ally-only -> ally target accepted, enemy target rejected
    ok_norm, ok_err = common_routes._normalize_target_by_skill(
        "S-AllyOnly",
        {"type": "single_slot", "slot_id": "S3"},
        state=state,
        source_slot_id="S1",
        allow_none=False,
    )
    assert ok_err is None
    assert ok_norm["slot_id"] == "S3"

    bad_norm, bad_err = common_routes._normalize_target_by_skill(
        "S-AllyOnly",
        {"type": "single_slot", "slot_id": "S2"},
        state=state,
        source_slot_id="S1",
        allow_none=False,
    )
    assert bad_norm is None
    assert bad_err

    # any -> both allowed
    any_norm, any_err = common_routes._normalize_target_by_skill(
        "S-Any",
        {"type": "single_slot", "slot_id": "S2"},
        state=state,
        source_slot_id="S1",
        allow_none=False,
    )
    assert any_err is None
    assert any_norm["slot_id"] == "S2"

