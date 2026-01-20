import unittest
import sys
import os
import types
from unittest.mock import MagicMock, patch

# --- Mock manager.utils ---
mock_utils = types.ModuleType('manager.utils')

def mock_get_status_value(char_obj, status_name):
    # Simple mock: look in status dict
    val = char_obj.get('status', {}).get(status_name)
    if val is not None: return val
    return 0

def mock_resolve_placeholders(text, char_obj):
    # Simple mock
    # Use mock_utils.get_status_value explicitly to hit the side_effect
    if '{物理補正}' in text:
        val = mock_utils.get_status_value(char_obj, '物理補正')
        text = text.replace('{物理補正}', str(val))
    if '{魔法補正}' in text:
        val = mock_utils.get_status_value(char_obj, '魔法補正')
        text = text.replace('{魔法補正}', str(val))
    return text

def mock_get_buff_stat_mod(char_obj, stat_name):
    return 0
def mock_get_buff_stat_mod_details(char_obj, stat_name):
    return []
def mock_set_status_value(char, name, val): pass
def mock_apply_buff(*args, **kwargs): pass
def mock_remove_buff(*args, **kwargs): pass

mock_utils.get_status_value = mock_get_status_value
mock_utils.set_status_value = mock_set_status_value
mock_utils.apply_buff = mock_apply_buff
mock_utils.remove_buff = mock_remove_buff
mock_utils.get_buff_stat_mod = mock_get_buff_stat_mod
mock_utils.get_buff_stat_mod_details = mock_get_buff_stat_mod_details
mock_utils.resolve_placeholders = mock_resolve_placeholders

sys.modules['manager.utils'] = mock_utils

# --- Mock manager.buff_catalog ---
mock_buff_catalog = types.ModuleType('manager.buff_catalog')
def mock_get_buff_effect(buff_name): return None
mock_buff_catalog.get_buff_effect = mock_get_buff_effect
sys.modules['manager.buff_catalog'] = mock_buff_catalog

# --- Mock plugins ---
# game_logic imports EFFECT_REGISTRY from plugins
mock_plugins = types.ModuleType('plugins')
mock_plugins.EFFECT_REGISTRY = {}
sys.modules['plugins'] = mock_plugins

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now import game_logic
from manager.game_logic import calculate_skill_preview

class TestUnifiedCalculation(unittest.TestCase):
    def setUp(self):
        self.actor = {
            'id': 'Actor1',
            'name': 'Hero',
            'status': {
                '物理補正': 2,
                '魔法補正': 0,
                '戦慄': 0,
            },
            'special_buffs': []
        }
        self.target = {'id': 'Target1', 'name': 'Villain'}
        self.skill_data = {
            '基礎威力': '5',
            'ダイス威力': '2d6',
            'チャットパレット': '【TestSkill】 5+2d6+{物理補正}'
        }

    def test_basic_calc(self):
        # Base 5, Dice 2d6, Phys 2. Total Mod = 2.
        # Range Min: 5 + 2(dice) + 2(mod) = 9
        # Range Max: 5 + 12(dice) + 2(mod) = 19
        preview = calculate_skill_preview(self.actor, self.target, self.skill_data)
        self.assertEqual(preview['min_damage'], 9)
        self.assertEqual(preview['max_damage'], 19)
        # 5+2d6+2
        self.assertEqual(preview['final_command'], "5+2d6+2")

    def test_external_mod(self):
        # External mod -2 to base power
        # Base 5 -> 3
        # Min: 3 + 2 + 2 = 7
        # Max: 3 + 12 + 2 = 17
        preview = calculate_skill_preview(self.actor, self.target, self.skill_data, external_base_power_mod=-2)
        self.assertEqual(preview['min_damage'], 7)
        self.assertEqual(preview['max_damage'], 17)
        self.assertTrue(preview['final_command'].startswith("3+"))

    def test_senritsu(self):
        self.actor['status']['戦慄'] = 2
        # Senritsu reduces dice faces by 2 (Max apply 3)
        # 2d6 -> 2d4
        # Base 5, Dice 2d4, Phys 2
        # Min: 5 + 2 + 2 = 9
        # Max: 5 + 8 + 2 = 15
        preview = calculate_skill_preview(self.actor, self.target, self.skill_data, senritsu_max_apply=3)
        self.assertEqual(preview['senritsu_dice_reduction'], 2)
        self.assertEqual(preview['max_damage'], 15)
        self.assertIn("2d4", preview['final_command'])

    @patch('manager.game_logic.get_status_value')
    @patch('manager.game_logic.get_buff_stat_mod') # Also mock this as it's used
    def test_correction_delta_calculation(self, mock_get_buff, mock_get_status):
        """物理/マグ補正が差分（Delta）として計算されるか検証"""
        actor = {
            "name": "TestActor",
            "params": [
                {"label": "基礎威力", "value": "10"},
                {"label": "物理補正", "value": "5"},
                {"label": "魔法補正", "value": "3"}
            ],
            "initial_data": {
                "物理補正": 5,
                "魔法補正": 3,
                "ダイス威力": 0
            },
            "special_buffs": []
        }

        # モックの設定
        mock_get_buff.return_value = 2

        def side_effect_get_status(char, stat):
            if stat == '物理補正': return 7
            if stat == '魔法補正': return 3
            if stat == '基礎威力': return 0
            if stat == 'ダイス威力': return 0
            if stat == '戦慄': return 0
            return 0
        mock_get_status.side_effect = side_effect_get_status

        # スキルデータ (物理補正を参照する)
        skill_data = {
            "基礎威力": 0,
            "ダイス威力": "2d6+{物理補正}",
            "チャットパレット": "TestSkill:2d6+{物理補正}"
        }

        # 実行
        result = calculate_skill_preview(actor, {}, skill_data)
        corrections = result.get('correction_details', [])

        # 検証
        # 物理補正は Delta = 7 (現在) - 5 (初期) = 2 となるはず
        phys_corr = next((c for c in corrections if c['source'] == '物理補正'), None)
        self.assertIsNotNone(phys_corr)
        self.assertEqual(phys_corr['value'], 2)

        # 魔法補正は Delta = 3 (現在) - 3 (初期) = 0 なので表示されないはず
        mag_corr = next((c for c in corrections if c['source'] == '魔法補正'), None)
        self.assertIsNone(mag_corr)

if __name__ == '__main__':
    unittest.main()
