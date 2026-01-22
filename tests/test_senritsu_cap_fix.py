
import sys
import os
import re

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock necessary modules
from unittest.mock import MagicMock

# Mock game_logic dependencies if needed, but we want to test the actual logic function
# However, calculate_skill_preview imports get_status_value etc.
# We will use the actual game_logic but mock the helper functions it imports if they are external
# Actually game_logic imports utils. Let's rely on actual utils if possible or mock them.

from manager import game_logic

# Mock get_status_value to return controlled values
def mock_get_status_value(char, param):
    if param == '戦慄':
        return char.get('senritsu', 0)
    if param == '物理補正': return 0
    if param == '魔法補正': return 0
    if param == 'ダイス威力': return 0
    return 0

# Patch utils
game_logic.get_status_value = mock_get_status_value
game_logic.get_buff_stat_mod = MagicMock(return_value=0)
game_logic.resolve_placeholders = lambda x, y: x # No placeholders

def test_senritsu_logic():
    print("Testing Senritsu Logic...")

    # Case 1: Senritsu 5, Cap 3 (Physical), Dice 2d6
    # Expect: reduction 3, faces 6->3
    char = {'senritsu': 5}
    skill = {'分類': '物理', 'ダイス威力': '2d6', '基礎威力': 0}

    res = game_logic.calculate_skill_preview(char, None, skill)

    print(f"Case 1 (Senritsu 5, Phy, 2d6): Reduction = {res['senritsu_dice_reduction']}")
    print(f"  Command: {res['final_command']}")

    if res['senritsu_dice_reduction'] == 3:
        print("  [PASS] Reduction capped at 3.")
    else:
        print(f"  [FAIL] Expected 3, got {res['senritsu_dice_reduction']}")

    # Case 2: Senritsu 5, Cap 3, Dice 1d2
    # Expect: reduction limit by faces. 2 - 1 = 1 max reduction.
    skill2 = {'分類': '物理', 'ダイス威力': '1d2', '基礎威力': 0}
    res2 = game_logic.calculate_skill_preview(char, None, skill2)

    print(f"Case 2 (Senritsu 5, Phy, 1d2): Reduction = {res2['senritsu_dice_reduction']}")
    print(f"  Command: {res2['final_command']}")

    if res2['senritsu_dice_reduction'] == 1:
        print("  [PASS] Reduction limited by faces (1d2 -> 1d1).")
    else:
        print(f"  [FAIL] Expected 1, got {res2['senritsu_dice_reduction']}")

    # Case 3: Senritsu 2, Cap 3, Dice 2d6
    # Expect: reduction 2
    char3 = {'senritsu': 2}
    res3 = game_logic.calculate_skill_preview(char3, None, skill)

    print(f"Case 3 (Senritsu 2, Phy, 2d6): Reduction = {res3['senritsu_dice_reduction']}")

    if res3['senritsu_dice_reduction'] == 2:
        print("  [PASS] Reduction matches current Senritsu (2).")
    else:
        print(f"  [FAIL] Expected 2, got {res3['senritsu_dice_reduction']}")

    # Case 4: Senritsu 5, Healing (No Tag), 2d6
    # Expect: reduction 0
    skill4 = {'分類': '回復', 'ダイス威力': '2d6', '基礎威力': 0}
    res4 = game_logic.calculate_skill_preview(char, None, skill4)

    print(f"Case 4 (Senritsu 5, Heal, 2d6): Reduction = {res4['senritsu_dice_reduction']}")

    if res4['senritsu_dice_reduction'] == 0:
        print("  [PASS] No reduction for non-physical/magical.")
    else:
        print(f"  [FAIL] Expected 0, got {res4['senritsu_dice_reduction']}")

if __name__ == "__main__":
    test_senritsu_logic()
