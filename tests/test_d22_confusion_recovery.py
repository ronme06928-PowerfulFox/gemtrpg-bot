from copy import deepcopy

import pytest

from manager.battle import common_manager
from manager.game_logic import apply_buff, compute_damage_multipliers
from plugins.standard import FearSurgeEffect
from plugins.buffs.confusion import ConfusionBuff
from tests.test_immediate_round_limit import _setup


CATALOG = {
    "Bu-02": {"id": "Bu-02", "name": "混乱", "default_duration": 2,
              "effect": {"type": "plugin", "name": "confusion", "damage_multiplier": 1.5,
                         "restore_mp_on_end": False}},
    "Bu-03": {"id": "Bu-03", "name": "混乱(戦慄殺到)", "default_duration": 2,
              "effect": {"type": "plugin", "name": "confusion", "damage_multiplier": 1.5,
                         "restore_mp_on_end": True}},
}


@pytest.mark.parametrize("buff_id", ["Bu-02", "Bu-03"])
def test_confusion_expiry_recovers_only_surge_version(monkeypatch, buff_id):
    state, actor, _emits, _snapshots = _setup(monkeypatch)
    actor["mp"] = 2
    actor["special_buffs"] = [{"buff_id": buff_id, "name": CATALOG[buff_id]["name"],
                               "lasting": 1, "delay": 0}]
    assert common_manager.process_full_round_end("room_t", "tester")
    assert actor["mp"] == (50 if buff_id == "Bu-03" else 2)
    assert actor["special_buffs"] == []
    # Repeated round-end cannot recover again.
    actor["mp"] = 1
    assert not common_manager.process_full_round_end("room_t", "tester")
    assert actor["mp"] == 1


def test_fear_surge_creates_recovering_confusion_and_keeps_restriction_and_multiplier(monkeypatch):
    monkeypatch.setattr("extensions.all_buff_data", deepcopy(CATALOG))
    actor = {"name": "target", "mp": 3, "maxMp": 10, "special_buffs": [],
             "states": [{"name": "戦慄", "value": 4}]}
    changes, _ = FearSurgeEffect().apply(actor, actor, {}, {})
    buff_change = next(c for c in changes if c[1] == "APPLY_BUFF")
    _, _, name, value = buff_change
    assert name == "混乱(戦慄殺到)"
    assert value["data"]["buff_id"] == "Bu-03"
    assert value["lasting"] == 2
    apply_buff(actor, name, value["lasting"], value["delay"], data=value["data"])
    assert ConfusionBuff.is_incapacitated(actor)
    assert compute_damage_multipliers({}, actor)["final"] == 1.5


@pytest.mark.parametrize("buff_id", ["Bu-02", "Bu-03"])
@pytest.mark.parametrize("delay", [0, 1])
def test_catalog_confusion_multiplier_is_applied_once(monkeypatch, buff_id, delay):
    monkeypatch.setattr("extensions.all_buff_data", deepcopy(CATALOG))
    actor = {"special_buffs": [{"name": CATALOG[buff_id]["name"], "buff_id": buff_id,
                               "lasting": 2, "delay": delay}]}
    assert compute_damage_multipliers({}, actor)["final"] == (1.5 if delay == 0 else 1.0)
