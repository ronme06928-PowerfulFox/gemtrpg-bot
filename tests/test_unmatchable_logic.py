import unittest
import sys
import os
import types
import json
from unittest.mock import MagicMock, patch

# ==========================================
# 1. Mock External Dependencies (Flask, SocketIO, SQLAlchemy)
# ==========================================
mock_flask = MagicMock()
mock_flask_globals = MagicMock()
mock_flask.globals = mock_flask_globals
sys.modules['flask'] = mock_flask
sys.modules['flask.globals'] = mock_flask_globals

mock_sqlalchemy_mod = MagicMock()
mock_sqlalchemy_mod.SQLAlchemy = MagicMock()
sys.modules['flask_sqlalchemy'] = mock_sqlalchemy_mod

mock_socketio_mod = MagicMock()
mock_emit = MagicMock()
mock_socketio_mod.emit = mock_emit
mock_socketio_mod.SocketIO = MagicMock()
sys.modules['flask_socketio'] = mock_socketio_mod

# ==========================================
# 2. Mock Application Extensions
# ==========================================
mock_extensions = types.ModuleType('extensions')
mock_socketio_obj = MagicMock()

def mock_on_decorator(*args, **kwargs):
    def decorator(f):
        return f
    return decorator
mock_socketio_obj.on.side_effect = mock_on_decorator
mock_extensions.socketio = mock_socketio_obj
mock_extensions.db = MagicMock()
mock_extensions.active_room_states = {}
mock_extensions.user_sids = {}

# Mock Skill Data
mock_skill_data = {
    'S-Unmatchable': {
        'name': 'Unmatchable Attack',
        'デフォルト名称': 'マッチ不可攻撃',
        '分類': '物理',
        'tags': ['マッチ不可'],
        '特記処理': '{"effects": []}'
    },
    'S-Attack': {
        'name': 'Normal Attack',
        'デフォルト名称': '通常攻撃',
        '分類': '物理',
        'tags': []
    },
    'S-Defense': {
        'name': 'Normal Defense',
        'デフォルト名称': '通常防御',
        '分類': '防御',
        'tags': []
    }
}
mock_extensions.all_skill_data = mock_skill_data
sys.modules['extensions'] = mock_extensions

# ==========================================
# 3. Mock Managers
# ==========================================
mock_rm = types.ModuleType('manager.room_manager')
test_room_state = {
    'characters': [
        {'id': 'ActorA', 'name': 'Attacker', 'status': {}, 'special_buffs': [], 'x':0, 'y':0, 'hp': 20, 'maxHp': 20},
        {'id': 'ActorD', 'name': 'Defender', 'status': {}, 'special_buffs': [], 'x':1, 'y':0, 'hp': 20, 'maxHp': 20}
    ],
    'active_match': None
}
def mock_get_room_state(room): return test_room_state
def mock_save_specific_room_state(room): pass
def mock_get_user_info(sid): return {'username': 'Tester', 'attribute': 'GM'}
def mock_update_char_stat(room, char, stat, val, *args, **kwargs):
    if stat == 'HP': char['hp'] = val
def mock_is_authorized(*args, **kwargs): return True

mock_rm.get_room_state = mock_get_room_state
mock_rm.save_specific_room_state = mock_save_specific_room_state
mock_rm.broadcast_state_update = MagicMock()
mock_rm.broadcast_log = MagicMock()
mock_rm.get_user_info_from_sid = mock_get_user_info
mock_rm._update_char_stat = mock_update_char_stat
mock_rm.is_authorized_for_character = mock_is_authorized
sys.modules['manager.room_manager'] = mock_rm

# manager.game_logic Mocks
mock_utils = types.ModuleType('manager.utils')
def mock_get_status_impl(c, n):
    if n == 'HP' or n == 'hp': return c.get('hp', 0)
    if n == 'MP' or n == 'mp': return c.get('mp', 0)
    return c.get(n, 0)
mock_utils.get_status_value = mock_get_status_impl
mock_utils.set_status_value = lambda c, n, v: c.update({n: v})
mock_utils.resolve_placeholders = lambda t, c: t
mock_utils.get_buff_stat_mod = lambda c, n: 0
mock_utils.get_buff_stat_mod_details = lambda c, n: []
mock_utils.apply_buff = MagicMock()
mock_utils.remove_buff = MagicMock()
mock_utils.calculate_buff_power_bonus = lambda *args: 0
mock_utils.calculate_damage_multiplier = lambda c: (1.0, [])
mock_utils.get_effective_origin_id = lambda c: 0
sys.modules['manager.utils'] = mock_utils

mock_buff_catalog = types.ModuleType('manager.buff_catalog')
mock_buff_catalog.get_buff_effect = lambda n: None
sys.modules['manager.buff_catalog'] = mock_buff_catalog

mock_plugins = types.ModuleType('plugins')
mock_plugins.EFFECT_REGISTRY = {}
sys.modules['plugins'] = mock_plugins

mock_buffs = types.ModuleType('plugins.buffs')
sys.modules['plugins.buffs'] = mock_buffs
mock_plugins.buffs = mock_buffs

mock_confusion = types.ModuleType('plugins.buffs.confusion')
mock_confusion.ConfusionBuff = MagicMock()
mock_confusion.ConfusionBuff.is_incapacitated.return_value = False
sys.modules['plugins.buffs.confusion'] = mock_confusion

mock_dodge = types.ModuleType('plugins.buffs.dodge_lock')
mock_dodge.DodgeLockBuff = MagicMock()
mock_dodge.DodgeLockBuff.has_re_evasion.return_value = False
sys.modules['plugins.buffs.dodge_lock'] = mock_dodge

mock_registry_mod = types.ModuleType('plugins.buffs.registry')
mock_registry_mod.buff_registry = MagicMock()
sys.modules['plugins.buffs.registry'] = mock_registry_mod
mock_buffs.registry = mock_registry_mod

mock_dice = types.ModuleType('manager.dice_roller')
mock_dice.roll_dice = lambda cmd: {'total': 10, 'details': '10', 'text': '10'}
sys.modules['manager.dice_roller'] = mock_dice

# Add path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load Real Modules
from manager.game_logic import calculate_skill_preview, process_skill_effects
sys.modules['manager.game_logic'].process_skill_effects = process_skill_effects
sys.modules['manager.game_logic'].get_status_value = mock_utils.get_status_value
sys.modules['manager.game_logic'].calculate_damage_multiplier = mock_utils.calculate_damage_multiplier

# Target Modules
import manager.battle.duel_solver as duel_solver
import manager.battle.wide_solver as wide_solver
wide_solver.calculate_damage_multiplier = mock_utils.calculate_damage_multiplier

class TestUnmatchableLogic(unittest.TestCase):
    def setUp(self):
        mock_rm.broadcast_log.reset_mock()
        # Reset Chars
        test_room_state['characters'][0]['hp'] = 20
        test_room_state['characters'][0]['hasActed'] = False
        test_room_state['characters'][1]['hp'] = 20
        test_room_state['characters'][1]['hasActed'] = False
        test_room_state['active_match'] = None

    def test_normal_match_mutual_one_sided(self):
        print("\n--- Test Normal Match Unmatchable (Mutual One-Sided) ---")
        room = 'test_room'
        # Attacker uses Unmatchable (10 dmg), Defender uses Attack (10 dmg)
        data = {
            'room': room,
            'match_id': 'm1',
            'actorIdA': 'ActorA', 'actorIdD': 'ActorD',
            'actorNameA': 'A', 'actorNameD': 'D',
            'commandA': '10', 'commandD': '10',
            'skillIdA': 'S-Unmatchable', 'skillIdD': 'S-Attack'
        }

        # Setup Active Match dummy (so execute checks pass)
        test_room_state['active_match'] = {'is_active': True, 'match_id': 'm1', 'executed': False}

        duel_solver.execute_duel_match(room, data, "GM")

        # Check HP: Both should take 10 damage
        # A: 20 -> 10, D: 20 -> 10
        self.assertEqual(test_room_state['characters'][0]['hp'], 10, "Attacker should take damage (Counter)")
        self.assertEqual(test_room_state['characters'][1]['hp'], 10, "Defender should take damage (Unmatchable Hit)")

        # Check Log
        args_list = mock_rm.broadcast_log.call_args_list
        found = False
        for args in args_list:
            if "相互一方攻撃" in args[0][1]:
                found = True
                break
        self.assertTrue(found, "Log should mention '相互一方攻撃'")

    def test_normal_match_mutual_one_sided_defense(self):
        print("\n--- Test Normal Match Unmatchable (Defender uses Defense) ---")
        room = 'test_room'
        # Attacker uses Unmatchable (10 dmg), Defender uses Defense (10 power)
        data = {
            'room': room,
            'match_id': 'm2',
            'actorIdA': 'ActorA', 'actorIdD': 'ActorD',
            'actorNameA': 'A', 'actorNameD': 'D',
            'commandA': '10', 'commandD': '10',
            'skillIdA': 'S-Unmatchable', 'skillIdD': 'S-Defense'
        }

        test_room_state['active_match'] = {'is_active': True, 'match_id': 'm2', 'executed': False}

        duel_solver.execute_duel_match(room, data, "GM")

        # Check HP:
        # A: 20 -> 20 (Defense skill deals 0 damage)
        # D: 20 -> 10 (Attacker hits)
        self.assertEqual(test_room_state['characters'][0]['hp'], 20, "Attacker should take 0 damage from Defense skill")
        self.assertEqual(test_room_state['characters'][1]['hp'], 10, "Defender should take damage")

    def test_wide_match_unmatchable_progression(self):
        print("\n--- Test Wide Match Unmatchable (Defenders marked hasActed) ---")
        room = 'test_room'

        # Setup active wide match
        defenders = [{
            'id': 'ActorD',
            'name': 'Defender',
            'declared': True,
            'skill_id': 'S-Defense',
            'command': '10'
        }]

        test_room_state['active_match'] = {
            'is_active': True,
            'match_type': 'wide',
            'attacker_id': 'ActorA',
            'defender_id': None,
            'attacker_declared': True,
            'defenders': defenders,
            'attacker_data': {
                'skill_id': 'S-Unmatchable',
                'final_command': '10'
            },
            'mode': 'individual'
        }
        test_room_state['characters'][0]['hasActed'] = False
        test_room_state['characters'][1]['hasActed'] = False

        wide_solver.execute_wide_match(room, "GM")

        # Check hasActed
        self.assertTrue(test_room_state['characters'][0]['hasActed'], "Attacker should have acted")
        self.assertTrue(test_room_state['characters'][1]['hasActed'], "Defender should have acted (even in Unmatchable)")

    def test_wide_match_unmatchable_damage(self):
        print("\n--- Test Wide Match Unmatchable (Damage Application) ---")
        room = 'test_room'

        # Attacker uses Unmatchable (Total 10)
        # Defender has 20 HP

        test_room_state['active_match'] = {
            'is_active': True,
            'match_type': 'wide',
            'attacker_id': 'ActorA',
            'defender_id': None,
            'attacker_declared': True,
            'defenders': [{
                'id': 'ActorD',
                'name': 'Defender',
                'declared': True,
                'skill_id': 'S-Defense',
                'command': '10'
            }],
            'attacker_data': {
                'skill_id': 'S-Unmatchable',
                'final_command': '10'
            },
            'mode': 'individual'
        }
        test_room_state['characters'][0]['hasActed'] = False
        test_room_state['characters'][1]['hasActed'] = False

        # Mock roll_dice to return total 10 so damage is 10
        # (Assuming roll_dice logic in wide_match uses standard call)
        mock_dice.roll_dice = lambda cmd: {'total': 10, 'details': '10', 'text': '10'}

        wide_solver.execute_wide_match(room, "GM")

        print(f"DEBUG: Attacker hasActed={test_room_state['characters'][0]['hasActed']}")
        print(f"DEBUG: Defender hasActed={test_room_state['characters'][1]['hasActed']}")
        print(f"DEBUG: Defender HP={test_room_state['characters'][1]['hp']}")

        # Check hasActed
        self.assertTrue(test_room_state['characters'][0]['hasActed'], "Attacker should have acted")
        self.assertTrue(test_room_state['characters'][1]['hasActed'], "Defender should have acted")

        # Check HP: Defender should take 10 damage (Unmatchable deals damage now)
        # 20 -> 10
        self.assertEqual(test_room_state['characters'][1]['hp'], 10, "Defender should take damage from Unmatchable Wide Attack")

if __name__ == '__main__':
    unittest.main()
