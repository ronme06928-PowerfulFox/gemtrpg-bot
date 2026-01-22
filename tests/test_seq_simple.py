"""
Test sequential effect processing with simplified output
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from manager.game_logic import process_skill_effects
from manager.utils import get_status_value, set_status_value

def test_sequential():
    results = []

    # Test 1
    results.append("=" * 60)
    results.append("Test 1: Initial rupture 3 -> Expected final 13")
    results.append("=" * 60)

    actor = {"id": "actor1", "name": "Attacker"}
    target = {
        "id": "target1",
        "name": "Target",
        "states": [{"name": "破裂", "value": 3}]
    }


    effects = [
        {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "破裂",
            "value": 5
        },
        {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "破裂",
            "value": 5,
            "condition": {
                "source": "target",
                "param": "破裂",
                "operator": "GTE",
                "value": 8
            }
        }
    ]

    bonus_dmg, logs, changes = process_skill_effects(effects, "HIT", actor, target)
    final = get_status_value(target, "破裂")

    results.append(f"Initial: 3")
    results.append(f"Final: {final}")
    results.append(f"Changes: {len(changes)}")
    results.append(f"Result: {'PASS' if final == 13 else 'FAIL - Expected 13'}")
    results.append("")

    # Test 2
    results.append("=" * 60)
    results.append("Test 2: Initial rupture 2 -> Expected final 7")
    results.append("=" * 60)

    target2 = {
        "id": "target2",
        "name": "Target2",
        "states": [{"name": "破裂", "value": 2}]
    }
    bonus_dmg2, logs2, changes2 = process_skill_effects(effects, "HIT", actor, target2)
    final2 = get_status_value(target2, "破裂")

    results.append(f"Initial: 2")
    results.append(f"Final: {final2}")
    results.append(f"Changes: {len(changes2)}")
    results.append(f"Result: {'PASS' if final2 == 7 else 'FAIL - Expected 7'}")
    results.append("")

    # Test 3
    results.append("=" * 60)
    results.append("Test 3: Initial rupture 8 -> Expected final 18")
    results.append("=" * 60)

    target3 = {
        "id": "target3",
        "name": "Target3",
        "states": [{"name": "破裂", "value": 8}]
    }
    bonus_dmg3, logs3, changes3 = process_skill_effects(effects, "HIT", actor, target3)
    final3 = get_status_value(target3, "破裂")

    results.append(f"Initial: 8")
    results.append(f"Final: {final3}")
    results.append(f"Changes: {len(changes3)}")
    results.append(f"Result: {'PASS' if final3 == 18 else 'FAIL - Expected 18'}")
    results.append("")

    results.append("=" * 60)
    results.append("Test Complete")
    results.append("=" * 60)

    # Write to file
    with open('test_results.txt', 'w', encoding='utf-8') as f:
        for line in results:
            f.write(line + '\n')
            print(line)

    print("\nResults written to test_results.txt")

if __name__ == "__main__":
    test_sequential()
