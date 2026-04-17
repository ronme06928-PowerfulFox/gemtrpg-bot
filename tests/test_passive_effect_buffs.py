from manager.utils import apply_passive_effect_buffs


def test_apply_passive_effect_buffs_expands_non_stat_effect_and_is_idempotent(monkeypatch):
    from manager.passives.loader import passive_loader

    monkeypatch.setattr(
        passive_loader,
        "load_passives",
        lambda *args, **kwargs: {
            "Pa-04": {
                "id": "Pa-04",
                "name": "氷断ち",
                "description": "対象に減速があれば与ダメ+20%",
                "effect": {
                    "stat_mods": {"行動回数": 1},
                    "outgoing_damage_multiplier": 1.2,
                    "condition": {
                        "source": "target",
                        "param": "buff_count:減速",
                        "operator": "GTE",
                        "value": 1,
                    },
                },
            }
        },
    )

    char = {
        "SPassive": ["Pa-04"],
        "special_buffs": [{"name": "既存バフ", "delay": 0, "lasting": 1}],
    }

    apply_passive_effect_buffs(char)
    apply_passive_effect_buffs(char)

    passive_rows = [b for b in char.get("special_buffs", []) if b.get("source") == "passive"]
    assert len(passive_rows) == 1
    row = passive_rows[0]
    assert row.get("passive_id") == "Pa-04"
    assert float(row.get("outgoing_damage_multiplier", 0)) == 1.2
    assert isinstance(row.get("condition"), dict)
    assert "stat_mods" not in row
    assert "stat_mods" not in (row.get("data") or {})
