import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# プロジェクトルートをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from manager.utils import get_status_value

class TestDynamicStatMods(unittest.TestCase):
    def setUp(self):
        # テスト用キャラクターデータ
        self.char = {
            'params': [
                {'label': '物理補正', 'value': 0},
                {'label': '魔法補正', 'value': 0}
            ],
            'states': [],
            'special_buffs': []
        }

    def test_base_value(self):
        """バフなしで基本値が取得できるか"""
        val = get_status_value(self.char, '物理補正')
        self.assertEqual(val, 0)

    @patch('manager.buff_catalog.get_buff_effect')
    def test_dynamic_phys_buff(self, mock_get_buff_effect):
        """_Physバフがステータスに反映されるか"""
        # モックの設定: Test_Phys5 -> 物理補正+5
        mock_get_buff_effect.return_value = {
            'stat_mods': {'物理補正': 5}
        }

        # バフ付与（stat_modsはまだ辞書に入っていない状態を想定 = 動的解決が必要）
        self.char['special_buffs'].append({
            'name': 'Test_Phys5',
            'lasting': 1,
            'delay': 0
        })

        val = get_status_value(self.char, '物理補正')
        self.assertEqual(val, 5)

    @patch('manager.buff_catalog.get_buff_effect')
    def test_dynamic_mag_down_buff(self, mock_get_buff_effect):
        """_MagDownバフがステータスに反映されるか"""
        # モックの設定: Test_MagDown3 -> 魔法補正-3
        mock_get_buff_effect.return_value = {
            'stat_mods': {'魔法補正': -3}
        }

        self.char['special_buffs'].append({
            'name': 'Test_MagDown3',
            'lasting': 1,
            'delay': 0
        })

        val = get_status_value(self.char, '魔法補正')
        self.assertEqual(val, -3)

    def test_cached_stat_mods(self):
        """既にstat_modsがキャッシュされているバフの動作確認"""
        # この場合は動的解決(mock)は呼ばれないはず
        self.char['special_buffs'].append({
            'name': 'Cached_Buff',
            'lasting': 1,
            'delay': 0,
            'stat_mods': {'物理補正': 10}
        })

        val = get_status_value(self.char, '物理補正')
        self.assertEqual(val, 10)

if __name__ == '__main__':
    unittest.main()
