# test_plugins_integration.py
"""
バフプラグイン統合テスト

各プラグインのスタティックメソッド呼び出しが正常に動作するか検証します。
"""

import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Import plugins
try:
    from plugins.buffs.confusion import ConfusionBuff
    from plugins.buffs.dodge_lock import DodgeLockBuff
    from plugins.buffs.burst_no_consume import BurstNoConsumeBuff
    print("[OK] Plugins imported successfully")
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    sys.exit(1)


class TestBuffPlugins(unittest.TestCase):

    def test_confusion_can_act(self):
        """ConfusionBuff.can_actのテスト"""
        print("\n--- Testing ConfusionBuff.can_act ---")

        # Case 1: No buffs
        char_normal = {'name': 'Normal', 'special_buffs': []}
        can_act, reason = ConfusionBuff.can_act(char_normal, {})
        self.assertTrue(can_act)
        print(f"[OK] Normal char can act")

        # Case 2: Confusion buff active
        char_confused = {
            'name': 'Confused',
            'special_buffs': [
                {'buff_id': 'Bu-02', 'name': '混乱', 'delay': 0, 'lasting': 1}
            ]
        }
        can_act, reason = ConfusionBuff.can_act(char_confused, {})
        self.assertFalse(can_act)
        self.assertEqual(reason, '混乱中のため行動できません')
        print(f"[OK] Confused char cannot act")

        # Case 3: Confusion buff with delay (should act)
        char_delayed = {
            'name': 'Delayed',
            'special_buffs': [
                {'buff_id': 'Bu-02', 'name': '混乱', 'delay': 1, 'lasting': 1}
            ]
        }
        can_act, reason = ConfusionBuff.can_act(char_delayed, {})
        self.assertTrue(can_act)
        print(f"[OK] Delayed confusion char can act")

    def test_dodge_lock_check(self):
        """DodgeLockBuff.has_re_evasionのテスト"""
        print("\n--- Testing DodgeLockBuff.has_re_evasion ---")

        # Case 1: Active
        char_locked = {
            'name': 'Locked',
            'special_buffs': [
                {'buff_id': 'Bu-05', 'name': '再回避ロック', 'delay': 0, 'lasting': 1, 'skill_id': 'Sk-01'}
            ]
        }
        self.assertTrue(DodgeLockBuff.has_re_evasion(char_locked))
        self.assertEqual(DodgeLockBuff.get_locked_skill_id(char_locked), 'Sk-01')
        print(f"[OK] Active dodge lock detected")

        # Case 2: Inactive (delay)
        char_delayed = {
            'name': 'Delayed',
            'special_buffs': [
                {'buff_id': 'Bu-05', 'name': '再回避ロック', 'delay': 1, 'lasting': 1}
            ]
        }
        self.assertFalse(DodgeLockBuff.has_re_evasion(char_delayed))
        print(f"[OK] Delayed dodge lock ignored")

    def test_burst_no_consume(self):
        """BurstNoConsumeBuff.has_burst_no_consumeのテスト"""
        print("\n--- Testing BurstNoConsumeBuff.has_burst_no_consume ---")

        # Case 1: Active
        char_active = {
            'name': 'Active',
            'special_buffs': [
                {'buff_id': 'Bu-06', 'name': '破裂威力減少無効', 'delay': 0, 'lasting': 1}
            ]
        }
        self.assertTrue(BurstNoConsumeBuff.has_burst_no_consume(char_active))
        print(f"[OK] Active burst no consume detected")


if __name__ == '__main__':
    unittest.main()
