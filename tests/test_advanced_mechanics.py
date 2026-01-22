import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from manager.game_logic import process_skill_effects, process_on_death, process_battle_start
# Mocking dependencies relies on them being importable or patched.

class TestAdvancedMechanics(unittest.TestCase):

    def setUp(self):
        self.room_name = "test_room"
        self.mock_char_a = {
            "id": "char_a", "name": "Alice", "type": "ally",
            "hp": 10, "maxHp": 10, "x": 0, "y": 0,
            "special_buffs": [], "states": []
        }
        self.mock_char_b = {
            "id": "char_b", "name": "Bob", "type": "ally",
            "hp": 10, "maxHp": 10, "x": 1, "y": 0,
            "special_buffs": [], "states": []
        }
        self.mock_char_c = {
            "id": "char_c", "name": "Charlie", "type": "ally",
            "hp": 10, "maxHp": 10, "x": 2, "y": 0,
            "special_buffs": [], "states": []
        }
        self.mock_char_e = {
            "id": "char_e", "name": "Enemy", "type": "enemy",
            "hp": 10, "maxHp": 10, "x": 3, "y": 0,
            "special_buffs": [], "states": []
        }

        self.mock_state = {
            "characters": [self.mock_char_a, self.mock_char_b, self.mock_char_c, self.mock_char_e],
            "timeline": ["char_a", "char_b", "char_c"]
        }

    @patch('manager.room_manager.get_room_state')
    def test_next_ally_targeting(self, mock_get_room_state):
        mock_get_room_state.return_value = self.mock_state

        # Effect definition targeting NEXT_ALLY
        effects = [{
            "timing": "TEST",
            "type": "APPLY_STATE",
            "target": "NEXT_ALLY",
            "state_name": "TestState",
            "value": 1
        }]

        # Context with room name
        context = {"characters": self.mock_state["characters"], "room": self.room_name}

        # 1. Alice -> Bob (Next in timeline)
        _, _, changes = process_skill_effects(effects, "TEST", self.mock_char_a, None, None, context)
        self.assertEqual(len(changes), 1)
        target, _, _, _ = changes[0]
        self.assertEqual(target['id'], "char_b")

        # 2. Bob -> Charlie
        _, _, changes = process_skill_effects(effects, "TEST", self.mock_char_b, None, None, context)
        target, _, _, _ = changes[0]
        self.assertEqual(target['id'], "char_c")

        # 3. Charlie -> Alice (Loop back)
        _, _, changes = process_skill_effects(effects, "TEST", self.mock_char_c, None, None, context)
        target, _, _, _ = changes[0]
        self.assertEqual(target['id'], "char_a")

    @patch('manager.game_logic.get_buff_effect')
    @patch('manager.room_manager.get_room_state')
    @patch('manager.room_manager.broadcast_log')
    @patch('manager.room_manager._update_char_stat')
    def test_process_on_death(self, mock_update, mock_log, mock_get_room_state, mock_get_buff):
        mock_get_room_state.return_value = self.mock_state

        # Mock Buff Definition
        mock_get_buff.return_value = {
            "name": "Curse",
            "on_death": [
                {
                    "timing": "IMMEDIATE",
                    "type": "APPLY_STATE",
                    "target": "ALL_ENEMIES", # Should target Enemy
                    "state_name": "CurseStack",
                    "value": 1
                }
            ]
        }

        # Give Alice the buff
        self.mock_char_a['special_buffs'].append({"name": "Curse"})

        # Trigger Death
        process_on_death(self.room_name, self.mock_char_a, "System")

        # Check if Enemy got the state
        # _update_char_stat called with (room, enemy_char, 'CurseStack', ...)
        # We need to verify arguments
        found = False
        for call in mock_update.call_args_list:
            args, _ = call
            if args[1]['id'] == 'char_e' and args[2] == 'CurseStack':
                found = True
                break
        self.assertTrue(found, "Enemy should receive CurseStack on Alice's death")

    @patch('manager.game_logic.get_buff_effect')
    @patch('manager.room_manager.get_room_state')
    @patch('manager.room_manager._update_char_stat')
    @patch('manager.room_manager.broadcast_log')
    @patch('manager.room_manager.save_specific_room_state')
    @patch('manager.room_manager.broadcast_state_update')
    def test_process_battle_start(self, mock_broadcast_update, mock_save, mock_log, mock_update, mock_get_room_state, mock_get_buff):
        mock_get_room_state.return_value = self.mock_state

        # Mock Passive Definition
        mock_get_buff.return_value = {
            "name": "InitFP",
            "battle_start_effect": [
                {
                    "type": "APPLY_STATE",
                    "state_name": "FP",
                    "value": 1
                }
            ]
        }

        # Give Alice the buff
        self.mock_char_a['special_buffs'].append({"name": "InitFP"})

        # Trigger Battle Start
        process_battle_start(self.room_name, self.mock_char_a)

        # Check update
        found = False
        for call in mock_update.call_args_list:
            args, _ = call
            if args[1]['id'] == 'char_a' and args[2] == 'FP' and args[3] >= 1: # current(0)+1
                found = True
                break
        self.assertTrue(found, "Alice should receive FP on battle start")

if __name__ == '__main__':
    unittest.main()
