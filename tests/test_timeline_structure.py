
import json
import uuid
import random

def test_structure():
    # Mocking data
    state = {
        'characters': [
            {'id': 'char1', 'name': 'Hero', 'x': 1, 'y': 1, 'hp': 100, 'params': [{'label': '速度', 'value': 10}], 'states': []},
            {'id': 'char2', 'name': 'Boss', 'x': 2, 'y': 2, 'hp': 1000, 'params': [{'label': '速度', 'value': 5}], 'states': [{'name': '行動回数', 'value': 2}]}
        ],
        'timeline': []
    }

    # Mocking get_status_value
    def get_status_value(char, name):
         # Simplified mock
         if name == '行動回数':
             for s in char.get('states', []):
                 if s['name'] == name: return int(s['value'])
             return 1
         if name == '速度':
             return 10
         return 0

    timeline_unsorted = []

    # Simulating process_round_start logic (from common_manager.py)
    for char in state['characters']:
        action_count = get_status_value(char, '行動回数')
        action_count = max(1, action_count)

        speed_param = get_status_value(char, '速度')
        initiative = speed_param // 6

        for i in range(action_count):
            roll = 3 # Fixed
            total_speed = initiative + roll
            entry_id = str(uuid.uuid4())

            timeline_unsorted.append({
                'id': entry_id,
                'char_id': char['id'],
                'speed': total_speed,
                'stat_speed': initiative,
                'roll': roll,
                'acted': False,
                'is_extra': (i > 0)
            })

    timeline_unsorted.sort(key=lambda x: x['speed'], reverse=True)
    state['timeline'] = timeline_unsorted

    # Serialize to JSON (simulate socket emit)
    serialized = json.dumps(state['timeline'], indent=2)
    print("Serialized Timeline:")
    print(serialized)

    # Check if char_id matches
    decoded = json.loads(serialized)
    for entry in decoded:
        print(f"Entry ID: {entry['id']}, Char ID: {entry['char_id']}, Acted: {entry['acted']}")

if __name__ == "__main__":
    test_structure()
