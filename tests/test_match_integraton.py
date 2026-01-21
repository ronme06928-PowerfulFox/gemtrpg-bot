import unittest
import sys
import os
import types
from unittest.mock import MagicMock, patch

# ==========================================
# 1. Mock External Dependencies (Flask, SocketIO)
# ==========================================
mock_flask = MagicMock()
mock_request = MagicMock()
mock_request.sid = 'test_sid'
mock_flask.request = mock_request
sys.modules['flask'] = mock_flask

mock_socketio_mod = MagicMock()
mock_emit = MagicMock()
mock_socketio_mod.emit = mock_emit
sys.modules['flask_socketio'] = mock_socketio_mod

# ==========================================
# 2. Mock Application Extensions
# ==========================================
mock_extensions = types.ModuleType('extensions')
mock_socketio_obj = MagicMock()

# Define identity decorator for .on
def mock_on_decorator(*args, **kwargs):
    def decorator(f):
        return f
    return decorator
mock_socketio_obj.on.side_effect = mock_on_decorator

mock_extensions.socketio = mock_socketio_obj

# Mock Skill Data
mock_skill_data = {
    'S-01': {
        'name': 'Test Attack',
        'デフォルト名称': 'テスト攻撃',
        '分類': '物理',
        '基礎威力': '5',
        'ダイス威力': '2d6',
        'チャットパレット': '【S-01】 5+2d6',
        'tags': [],
        '特記処理': '{"effects": [{"type": "MODIFY_BASE_POWER", "value": 2}]}'
    },
    'S-02': {
        'name': 'Test Defense',
        'デフォルト名称': 'テスト防御',
        '分類': '防御',
        '基礎威力': '0',
        'ダイス威力': '1d6',
        'チャットパレット': '【S-02】 1d6',
        'tags': []
    }
}
mock_extensions.all_skill_data = mock_skill_data
sys.modules['extensions'] = mock_extensions

# ==========================================
# 3. Mock Managers
# ==========================================
# manager.room_manager
mock_rm = types.ModuleType('manager.room_manager')
test_room_state = {
    'characters': [
        {'id': 'ActorA', 'name': 'Attacker', 'status': {}, 'special_buffs': [], 'x':0, 'y':0, 'hp': 20},
        {'id': 'ActorD', 'name': 'Defender', 'status': {}, 'special_buffs': [], 'x':1, 'y':0, 'hp': 20}
    ],
    'active_match': None
}
def mock_get_room_state(room): return test_room_state
def mock_save_specific_room_state(room): pass
def mock_get_user_info(sid): return {'username': 'Tester', 'attribute': 'GM'}
def mock_update_char_stat(*args, **kwargs): pass
def mock_is_authorized(*args, **kwargs): return True

mock_rm.get_room_state = mock_get_room_state
mock_rm.save_specific_room_state = mock_save_specific_room_state
mock_rm.broadcast_state_update = MagicMock()
mock_rm.broadcast_log = MagicMock()
mock_rm.get_user_info_from_sid = mock_get_user_info
mock_rm._update_char_stat = mock_update_char_stat
mock_rm.is_authorized_for_character = mock_is_authorized
mock_rm.get_all_users = MagicMock(return_value=[]) # Needed if core uses it?
sys.modules['manager.room_manager'] = mock_rm

# manager.game_logic
mock_utils = types.ModuleType('manager.utils')
mock_utils.get_status_value = lambda c, n: c['status'].get(n, 0)
mock_utils.set_status_value = lambda c, n, v: c['status'].update({n: v})
mock_utils.resolve_placeholders = lambda t, c: t
mock_utils.get_buff_stat_mod = lambda c, n: 0
mock_utils.get_buff_stat_mod_details = lambda c, n: []
mock_utils.apply_buff = MagicMock()
mock_utils.remove_buff = MagicMock()
mock_utils.calculate_buff_power_bonus = lambda *args: 0
mock_utils.calculate_damage_multiplier = lambda c: (1.0, [])
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

sys.modules['plugins.buffs.dodge_lock'] = mock_dodge

# Mock plugins.buffs.registry
mock_registry_mod = types.ModuleType('plugins.buffs.registry')
mock_registry_mod.buff_registry = MagicMock()
sys.modules['plugins.buffs.registry'] = mock_registry_mod
mock_buffs.registry = mock_registry_mod


mock_dice = types.ModuleType('manager.dice_roller')
mock_dice.roll_dice = lambda cmd: {'total': 10, 'details': '10', 'text': '10'}
sys.modules['manager.dice_roller'] = mock_dice

# Add path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import Real Modules for Logic
from manager.game_logic import calculate_skill_preview, process_skill_effects
sys.modules['manager.game_logic'].calculate_skill_preview = calculate_skill_preview
sys.modules['manager.game_logic'].process_skill_effects = process_skill_effects
sys.modules['manager.game_logic'].get_status_value = mock_utils.get_status_value # Inject
sys.modules['manager.game_logic'].calculate_damage_multiplier = mock_utils.calculate_damage_multiplier

# Target Modules (New Routes)
import events.battle.duel_routes as dr
import manager.battle.duel_solver as ds

class TestMatchIntegration(unittest.TestCase):
    def setUp(self):
        mock_extensions.socketio.reset_mock()
        mock_rm.broadcast_log.reset_mock()
        test_room_state['active_match'] = {
            'is_active': True,
            'match_type': 'duel',
            'attacker_id': 'ActorA',
            'defender_id': 'ActorD',
            'match_id': 'test-match-uuid',
            'attacker_declared': False,
            'defender_declared': False
        }

    def test_full_match_flow(self):
        print("\n--- Testing Full Match Flow (Refactored) ---")
        room = 'room1'
        # 1. Attacker Declares (Commit)
        print("1. Attacker Declares")
        dr.on_declare_skill({
            'room': room,
            'skill_id': 'S-01',
            'prefix': 'attacker',
            'commit': True
        })

        if 'attacker_declared' not in test_room_state['active_match'] or not test_room_state['active_match']['attacker_declared']:
            print("FAILURE: Attacker declared flag not set.")

        self.assertTrue(test_room_state['active_match'].get('attacker_declared'))

        # 2. Defender Declares (Commit)
        print("2. Defender Declares")
        dr.on_declare_skill({
            'room': room,
            'skill_id': 'S-02',
            'prefix': 'defender',
            'commit': True
        })

        self.assertTrue(test_room_state['active_match']['defender_declared'])

        # 3. Manual Execution Trigger
        # The refactoring moved to manual execution or explicit event
        print("3. Execute Match")

        # Mocking execute_duel_match is not needed if we want to test IT logic,
        # but we mocked manager.battle.core which is used by it.
        # We need to ensure execute_duel_match logic is reached.

        # We'll spy on execute_duel_match by wrapping it?
        # Or just checking broadcast_log call from real execution.

        dr.on_request_match({
            'room': room,
            'match_id': 'test-match-uuid',
            'commandA': '10',
            'commandB': '10', # Typo in legacy test? duel_solver uses commandD
            'commandD': '10',
            'actorIdA': 'ActorA',
            'actorIdD': 'ActorD',
            'actorNameA': 'Attacker',
            'actorNameD': 'Defender',
            'skillIdA': 'S-01',
            'skillIdD': 'S-02'
        })

        # Verify broadcast log
        args_list = mock_rm.broadcast_log.call_args_list
        match_log_found = False
        for args in args_list:
            if len(args[0]) >= 3 and args[0][2] == 'match':
                match_log_found = True
                print(f"Match Log Found: {args[0][1]}")

        self.assertTrue(match_log_found, "Match result log was not broadcasted")

if __name__ == '__main__':
    unittest.main()
