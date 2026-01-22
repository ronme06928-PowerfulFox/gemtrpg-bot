import sys
import os
import json
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())

# Mock modules that might cause issues
sys.modules['extensions'] = MagicMock()
sys.modules['flask'] = MagicMock()

# Import logic
from manager.game_logic import process_skill_effects
from manager.utils import get_status_value, set_status_value
from plugins import EFFECT_REGISTRY

def test_pb05_logic():
    print("--- Testing Pb-05 Burst Logic ---")

    # Setup Data
    actor = {"id": "actor1", "name": "Attacker", "states": [], "params": []}
    target = {"id": "target1", "name": "Target", "states": [{"name": "破裂", "value": 10}], "params": []}

    # Skill Data (Pb-05 partial definition)
    # "[的中時]破裂爆発。この破裂爆発は対象の破裂の値を半分にする。破裂爆発。"
    effects = [
        {
            "timing": "HIT",
            "type": "CUSTOM_EFFECT",
            "value": "破裂爆発",
            "rupture_remainder_ratio": 0.5
        },
        {
            "timing": "HIT",
            "type": "CUSTOM_EFFECT",
            "value": "破裂爆発"
        }
    ]

    print(f"Initial Rupture: {get_status_value(target, '破裂')}")

    # Execute Process
    total_damage, logs, changes = process_skill_effects(effects, "HIT", actor, target, context={"registry": EFFECT_REGISTRY})

    print(f"Logs: {logs}")
    print(f"Changes: {changes}")
    print(f"Total Bonus Damage (from burst): {total_damage}") # Note: Burst returns CUSTOM_DAMAGE, which is summed in 'changes' usually, but 'process_skill_effects' returns tuple (dmg, logs, changes).
    # Wait, process_skill_effects returns (total_damage, log_snippets, changes_to_apply)
    # Does it auto-sum CUSTOM_DAMAGE?
    # Let's check process_skill_effects implementation in game_logic.py
    # ...
    # handler returns (changes, logs)
    # process_skill_effects extends logs, extends changes.
    # It does NOT sum damage itself. It returns changes.
    # The caller (duel_solver) sums custom damage.

    damage_sum = 0
    for c in changes:
        if c[1] == "CUSTOM_DAMAGE":
            damage_sum += c[3]

    print(f"Calculated Damage Sum: {damage_sum}")
    print(f"Final Rupture Stat (in object): {get_status_value(target, '破裂')}")

    # Expected:
    # 1. Burst (10) -> Rupture becomes 5. Damage 10.
    # 2. Burst (5) -> Rupture becomes 0. Damage 5.
    # Total Damage 15. Final Rupture 0.

    if damage_sum == 15 and get_status_value(target, '破裂') == 0:
        print("[SUCCESS] Logic works as expected for 'damage = current'.")
    elif damage_sum == 10 and get_status_value(target, '破裂') == 0:
         print("[RESULT] Logic might be 'damage = consumed'?")
    else:
        print(f"[FAILURE] Unexpected result.")

if __name__ == "__main__":
    test_pb05_logic()
