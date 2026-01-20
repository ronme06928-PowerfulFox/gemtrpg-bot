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
        '特記処理': '{"effects": [{"type": "MODIFY_BASE_POWER", "value": 2}]}' # Test effect
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
def mock_is_authorized(*args, **kwargs): return True # Always authorized

mock_rm.get_room_state = mock_get_room_state
mock_rm.save_specific_room_state = mock_save_specific_room_state
mock_rm.broadcast_state_update = MagicMock()
mock_rm.broadcast_log = MagicMock()
mock_rm.get_user_info_from_sid = mock_get_user_info
mock_rm._update_char_stat = mock_update_char_stat
mock_rm.is_authorized_for_character = mock_is_authorized
sys.modules['manager.room_manager'] = mock_rm

# manager.game_logic
# Import actual if possible, but mock for now to avoid complexity in test environment
# However, we want to test the FLOW, so we need some logic.
# Use REAL game_logic but mock its imports if passed.
# Since we are running valid python code, let's try to import the real one?
# But checking `calculate_skill_preview` is key.
# Let's mock it to return predictable results, OR use the real one if accessible.
# Given complexity, we will use the REAL game_logic but mock its utils.

mock_utils = types.ModuleType('manager.utils')
mock_utils.get_status_value = lambda c, n: c['status'].get(n, 0)
mock_utils.set_status_value = lambda c, n, v: c['status'].update({n: v})
mock_utils.resolve_placeholders = lambda t, c: t
mock_utils.get_buff_stat_mod = lambda c, n: 0
mock_utils.get_buff_stat_mod_details = lambda c, n: []
mock_utils.apply_buff = MagicMock()
mock_utils.remove_buff = MagicMock()
mock_utils.calculate_buff_power_bonus = lambda *args: 0
sys.modules['manager.utils'] = mock_utils

mock_buff_catalog = types.ModuleType('manager.buff_catalog')
mock_buff_catalog.get_buff_effect = lambda n: None
sys.modules['manager.buff_catalog'] = mock_buff_catalog

mock_plugins = types.ModuleType('plugins')
mock_plugins.EFFECT_REGISTRY = {}
sys.modules['plugins'] = mock_plugins

# Mock plugins.buffs
mock_buffs = types.ModuleType('plugins.buffs')
sys.modules['plugins.buffs'] = mock_buffs
mock_plugins.buffs = mock_buffs

# Mock plugins.buffs.confusion
mock_confusion = types.ModuleType('plugins.buffs.confusion')
mock_confusion_buff_class = MagicMock()
mock_confusion_buff_class.can_act.return_value = (True, "")
mock_confusion_buff_class.is_incapacitated.return_value = False
mock_confusion.ConfusionBuff = mock_confusion_buff_class
sys.modules['plugins.buffs.confusion'] = mock_confusion
mock_buffs.confusion = mock_confusion

# Mock plugins.buffs.dodge_lock
mock_dodge = types.ModuleType('plugins.buffs.dodge_lock')
mock_dodge_buff_class = MagicMock()
mock_dodge_buff_class.get_locked_skill_id.return_value = None
mock_dodge_buff_class.has_re_evasion.return_value = False
mock_dodge.DodgeLockBuff = mock_dodge_buff_class
sys.modules['plugins.buffs.dodge_lock'] = mock_dodge
mock_buffs.dodge_lock = mock_dodge

mock_effects = types.ModuleType('manager.skill_effects')
mock_effects.apply_skill_effects_bidirectional = MagicMock(return_value=(0, []))
sys.modules['manager.skill_effects'] = mock_effects

mock_dice = types.ModuleType('manager.dice_roller')
mock_dice.roll_dice = lambda cmd: {'total': 10, 'text': '10'} # Fixed roll
sys.modules['manager.dice_roller'] = mock_dice

# Add path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import Real Modules
from manager.game_logic import calculate_skill_preview, process_skill_effects
# Inject real functions into mocked module so socket_battle uses them
sys.modules['manager.game_logic'].calculate_skill_preview = calculate_skill_preview
sys.modules['manager.game_logic'].process_skill_effects = process_skill_effects
sys.modules['manager.game_logic'].get_status_value = mock_utils.get_status_value
sys.modules['manager.game_logic'].set_status_value = mock_utils.set_status_value

# Import target module
import events.socket_battle as sb
sb.socketio = MagicMock() # Patch directly

class TestMatchIntegration(unittest.TestCase):
    def setUp(self):
        # Reset Mock
        sb.socketio.reset_mock()
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
        print("\n--- Testing Full Match Flow ---")
        room = 'room1'

        # 1. Attacker Declares (Commit)
        print("1. Attacker Declares")
        sb.handle_skill_declaration({
            'room': room,
            'actor_id': 'ActorA',
            'target_id': 'ActorD',
            'skill_id': 'S-01',
            'prefix': 'attacker',
            'commit': True
        })

        if 'attacker_declared' not in test_room_state['active_match'] or not test_room_state['active_match']['attacker_declared']:
            print("FAILURE: Attacker declared flag not set.")
            print("Emit calls:", sb.socketio.emit.call_args_list)

        # Check if declared flag is set
        self.assertTrue(test_room_state['active_match'].get('attacker_declared'))
        self.assertIn('attacker_data', test_room_state['active_match'])

        # 2. Defender Declares (Commit) -> Should trigger execution
        print("2. Defender Declares")

        # Mock handle_match execution to verify it's called
        original_handle_match = sb.handle_match
        mock_handle_match = MagicMock(side_effect=original_handle_match)
        sb.handle_match = mock_handle_match

        sb.handle_skill_declaration({
            'room': room,
            'actor_id': 'ActorD',
            'target_id': 'ActorA',
            'skill_id': 'S-02',
            'prefix': 'defender',
            'commit': True
        })

        self.assertTrue(test_room_state['active_match']['defender_declared'])

        # 3. Verify Execution Triggered
        # execute_match_from_active_state should have been called, which calls handle_match
        print("3. Verification")
        if mock_handle_match.called:
            print("SUCCESS: handle_match was called!")
            call_args = mock_handle_match.call_args[0][0]
            print(f"Called with: {call_args}")

            # 4. Verify IDs are passed
            self.assertEqual(call_args.get('skillIdA'), 'S-01')
            self.assertEqual(call_args.get('skillIdD'), 'S-02')

            # 5. Verify Result Emission
            # Check if match result log was broadcasted
            # handle_match calls broadcast_log with type 'match'
            args_list = mock_rm.broadcast_log.call_args_list
            match_log_found = False
            for args in args_list:
                if len(args[0]) >= 3 and args[0][2] == 'match':
                    match_log_found = True
                    print(f"Match Log Found: {args[0][1]}")

            self.assertTrue(match_log_found, "Match result log was not broadcasted")

            # ★ Verify Correction Details (Aggregation)
            # Find 'skill_declaration_result' or 'match_data_updated' emission
            decl_emits = [call for call in sb.socketio.emit.call_args_list if call[0][0] == 'match_data_updated']
            if decl_emits:
                 last_emit = decl_emits[-1]
                 data = last_emit[0][1].get('data', {})
                 print("Emitted Data Keys:", data.keys())
                 if 'correction_details' in data:
                     print("Correction Details:", data['correction_details'])
                     # Check aggregation format (source/value)
                     for d in data['correction_details']:
                         self.assertIn('source', d)
                         self.assertIn('value', d)
                 else:
                     print("WARNING: correction_details not found in sync emission")

        else:
            print("FAILURE: handle_match was NOT called.")
            self.fail("Match execution was not triggered.")

        # Cleanup
        sb.handle_match = original_handle_match

if __name__ == '__main__':
    unittest.main()
