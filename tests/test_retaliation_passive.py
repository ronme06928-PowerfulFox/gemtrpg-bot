from manager.battle import runtime_actions
def _char(name, hp=20, buffs=None, states=None):
    return {
        "name": name,
        "hp": hp,
        "maxHp": hp,
        "params": [
            {"label": "FP", "value": 0},
            {"label": "\u51fa\u8840", "value": 0},
            {"label": "\u4e80\u88c2", "value": 0},
            {"label": "\u6226\u6144", "value": 0},
        ],
        "states": list(states or []),
        "special_buffs": list(buffs or []),
    }


def _fake_update(_room, char, stat_name, new_value, username=None, **_kwargs):
    _ = username
    if stat_name == "HP":
        char["hp"] = int(new_value)
        return
    states = char.setdefault("states", [])
    for row in states:
        if row.get("name") == stat_name:
            row["value"] = int(new_value)
            return
    states.append({"name": stat_name, "value": int(new_value)})


def _state_value(char, name):
    for row in char.get("states", []):
        if row.get("name") == name:
            return int(row.get("value", 0))
    for row in char.get("params", []):
        if row.get("label") == name:
            return int(row.get("value", 0))
    return 0


def _capture_broadcast_logs(monkeypatch):
    messages = []

    def _fake_broadcast(_room, message, *_args, **_kwargs):
        messages.append(str(message))

    monkeypatch.setattr(runtime_actions, "broadcast_log", _fake_broadcast)
    return messages


def test_on_damage_reaction_damages_attacker(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalHide",
                "delay": 0,
                "data": {"on_damage_reaction": {"target": "attacker", "damage": 2}},
            }
        ],
    )
    attacker = _char("Attacker", hp=12)

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)
    broadcast_messages = _capture_broadcast_logs(monkeypatch)

    logs = []
    extra_damage = runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=attacker,
    )

    line = "[\u88ab\u5f3e\u53cd\u5fdc] CrystalScorpion\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067Attacker\u306b2\u30c0\u30e1\u30fc\u30b8\u3002"
    assert extra_damage == 0
    assert attacker["hp"] == 10
    assert line in logs
    assert line in broadcast_messages


def test_on_damage_reaction_applies_bleed_to_attacker(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalBleedHide",
                "delay": 0,
                "data": {
                    "on_damage_reaction": {
                        "target": "attacker",
                        "apply_state": [{"name": "\u51fa\u8840", "value": 3}],
                    }
                },
            }
        ],
    )
    attacker = _char("Attacker", hp=12)

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)
    broadcast_messages = _capture_broadcast_logs(monkeypatch)
    logs = []

    runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=attacker,
    )

    line = "[\u88ab\u5f3e\u53cd\u5fdc] CrystalScorpion\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067Attacker\u306b\u51fa\u88403\u3092\u4ed8\u4e0e\u3002"
    assert _state_value(attacker, "\u51fa\u8840") == 3
    assert line in logs
    assert line in broadcast_messages


def test_on_damage_reaction_applies_fissure_round_buff_to_attacker(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalFissureHide",
                "delay": 0,
                "data": {
                    "on_damage_reaction": {
                        "target": "attacker",
                        "apply_state": [{"name": "\u4e80\u88c2", "value": 2, "rounds": 3}],
                    }
                },
            }
        ],
    )
    attacker = _char("Attacker", hp=12)

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)
    broadcast_messages = _capture_broadcast_logs(monkeypatch)

    logs = []
    runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=attacker,
    )

    line = "[\u88ab\u5f3e\u53cd\u5fdc] CrystalScorpion\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067Attacker\u306b3\u30e9\u30a6\u30f3\u30c9\u306e\u4e80\u88c22\u3092\u4ed8\u4e0e\u3002"
    assert _state_value(attacker, "\u4e80\u88c2") == 2
    fissure_buckets = [b for b in attacker.get("special_buffs", []) if b.get("buff_id") == "Bu-Fissure"]
    assert len(fissure_buckets) == 1
    assert fissure_buckets[0]["lasting"] == 3
    assert fissure_buckets[0]["count"] == 2
    assert line in logs
    assert line in broadcast_messages


def test_on_damage_reaction_skips_positive_fissure_without_rounds(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalFissureHide",
                "delay": 0,
                "data": {
                    "on_damage_reaction": {
                        "target": "attacker",
                        "apply_state": [{"name": "\u4e80\u88c2", "value": 2}],
                    }
                },
            }
        ],
    )
    attacker = _char("Attacker", hp=12)

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)
    broadcast_messages = _capture_broadcast_logs(monkeypatch)

    logs = []
    runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=attacker,
    )

    line = "[\u88ab\u5f3e\u53cd\u5fdc] CrystalScorpion\u306e\u88ab\u5f3e\u53cd\u5fdc\u306f\u767a\u52d5\u3057\u305f\u304c\u3001Attacker\u3078\u306e\u52b9\u679c\u306f\u4e0d\u767a\u3002(\u4e80\u88c2\u306f\u7d99\u7d9a\u30e9\u30a6\u30f3\u30c9\u672a\u6307\u5b9a)"
    assert _state_value(attacker, "\u4e80\u88c2") == 0
    assert not [b for b in attacker.get("special_buffs", []) if b.get("buff_id") == "Bu-Fissure"]
    assert line in logs
    assert line in broadcast_messages


def test_on_damage_reaction_is_suppressed_by_context(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalHide",
                "delay": 0,
                "data": {"on_damage_reaction": {"target": "attacker", "damage": 2}},
            }
        ],
    )
    attacker = _char("Attacker", hp=12)

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)
    broadcast_messages = _capture_broadcast_logs(monkeypatch)

    logs = []
    runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=attacker,
        context={"damage_source": "on_damage_reaction"},
    )

    assert attacker["hp"] == 12
    assert logs == []
    assert broadcast_messages == []


def test_on_damage_reaction_requires_attacker_target(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalHide",
                "delay": 0,
                "data": {"on_damage_reaction": {"target": "attacker", "damage": 2}},
            }
        ],
    )

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)
    broadcast_messages = _capture_broadcast_logs(monkeypatch)

    logs = []
    runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=None,
    )

    assert logs == []
    assert broadcast_messages == []


def test_on_damage_reaction_apply_buff_id_only(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalTestHide",
                "delay": 0,
                "data": {
                    "on_damage_reaction": {
                        "target": "attacker",
                        "apply_buff": [
                            {
                                "buff_id": "Bu-TestReaction",
                                "lasting": 2,
                                "delay": 0,
                            }
                        ],
                    }
                },
            }
        ],
    )
    attacker = _char("Attacker", hp=12)

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)
    broadcast_messages = _capture_broadcast_logs(monkeypatch)

    logs = []
    runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=attacker,
    )

    matched = [b for b in attacker.get("special_buffs", []) if b.get("buff_id") == "Bu-TestReaction"]
    assert len(matched) == 1
    assert matched[0]["lasting"] == 2

    line = "[被弾反応] CrystalScorpionの被弾反応でAttackerにBu-TestReactionを付与。"
    assert line in logs
    assert line in broadcast_messages


def test_on_damage_reaction_apply_buff_data_count(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalChargeHide",
                "delay": 0,
                "data": {
                    "on_damage_reaction": {
                        "target": "attacker",
                        "apply_buff": [
                            {
                                "buff_id": "Bu-ChargeReaction",
                                "buff_name": "蓄力",
                                "lasting": 1,
                                "delay": 0,
                                "data": {"count": 3},
                            }
                        ],
                    }
                },
            }
        ],
    )
    attacker = _char("Attacker", hp=12)

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)
    broadcast_messages = _capture_broadcast_logs(monkeypatch)

    logs = []
    runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=attacker,
    )

    matched = [b for b in attacker.get("special_buffs", []) if b.get("buff_id") == "Bu-ChargeReaction"]
    assert len(matched) == 1
    assert matched[0].get("count") == 3

    line = "[被弾反応] CrystalScorpionの被弾反応でAttackerに蓄力を付与。"
    assert line in logs
    assert line in broadcast_messages
