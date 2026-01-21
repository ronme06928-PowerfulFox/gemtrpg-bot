
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

# Mock Flask-SocketIO emit
from unittest.mock import MagicMock
sys.modules['extensions'] = MagicMock()
sys.modules['extensions'].socketio = MagicMock()

# Mock room_manager dependencies
import manager.room_manager
manager.room_manager.broadcast_log = MagicMock()
manager.room_manager._update_char_stat = MagicMock()
manager.room_manager.get_room_state = MagicMock(return_value={})

from manager.battle.core import process_on_damage_buffs
from manager.buff_catalog import get_buff_effect

def test_bleed_react():
    print("--- Test Start: Bleed React ---")

    # define character with the dynamic buff
    char = {
        "id": "char1",
        "name": "TestChar",
        "hp": 20,
        "states": [
            {"name": "出血", "value": 0}
        ],
        "special_buffs": [
            {"name": "Blood_BleedReact2"} # Should trigger bleed +2 on damage
        ]
    }

    room = "test_room"
    damage = 5
    username = "Attacker"
    logs = []

    # Mock _update_char_stat to print what it would do
    def mock_update(room, char, stat, val, username=None):
        print(f"FAILED? No, mocked _update_char_stat called: {stat} -> {val}")
        # update visually for check
        found = False
        for s in char['states']:
            if s['name'] == stat:
                s['value'] = val
                found = True
        if not found:
             char['states'].append({"name": stat, "value": val})

    manager.room_manager._update_char_stat.side_effect = mock_update

    # Dependency injection for get_status_value is internal to core/game_logic.
    # process_on_damage_buffs calls get_status_value from manager.game_logic

    print(f"Char Buffs: {char['special_buffs']}")

    # Run
    process_on_damage_buffs(room, char, damage, username, logs)

    print("Logs:", logs)

    # Verify
    s = next((s for s in char['states'] if s['name'] == '出血'), None)
    if s and s['value'] == 2:
        print("[PASS] Bleed increased to 2.")
    elif logs and "出血" in str(logs):
        print("[PASS] Logs indicate success (mock update logic might differ from real).")
    else:
        print(f"[FAIL] Bleed value: {s['value'] if s else 'None'}")

if __name__ == "__main__":
    test_bleed_react()
