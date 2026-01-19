# tests/test_item_effects.py
"""
アイテム効果のテストコード
"""

import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from plugins.items import get_effect_handler

def create_test_char(name, hp=50, max_hp=100, mp=20, max_mp=30, char_type='ally'):
    """テスト用キャラクターを作成"""
    return {
        'id': f'test_{name}',
        'name': name,
        'type': char_type,
        'hp': hp,
        'maxHp': max_hp,
        'mp': mp,
        'maxMp': max_mp,
        'states': [
            {'name': 'FP', 'value': 5},
            {'name': '出血', 'value': 3},
            {'name': '破裂', 'value': 2},
            {'name': '亀裂', 'value': 4}
        ]
    }

def print_test_header(test_name):
    """テストヘッダーを表示"""
    print(f"\n{'='*60}")
    print(f"テスト: {test_name}")
    print(f"{'='*60}")

def print_result(result):
    """結果を表示"""
    print(f"\n成功: {result['success']}")
    print(f"消費: {result['consumed']}")
    print(f"\n変更:")
    for change in result['changes']:
        print(f"  - {change['field']}: {change['old']} → {change['new']} (Δ{change['delta']})")
    print(f"\nログ:")
    for log in result['logs']:
        print(f"  [{log['type']}] {log['message']}")

# ======================================
# テスト1: HP回復（単体）
# ======================================
def test_heal_single():
    print_test_header("HP回復（単体）")

    user = create_test_char("勇者", hp=30)
    target = create_test_char("戦士", hp=40)

    item_data = {
        'id': 'I-TEST-01',
        'name': 'ポーション',
        'consumable': True,
        'effect': {
            'type': 'heal',
            'target': 'single',
            'hp': 20
        }
    }

    context = {
        'room': 'test_room',
        'all_characters': [user, target]
    }

    handler = get_effect_handler('heal')
    result = handler.apply(user, target, item_data, item_data['effect'], context)

    print_result(result)
    print(f"\n対象のHP: {target['hp']} / {target['maxHp']}")

# ======================================
# テスト2: HP/MP/FP複合回復
# ======================================
def test_heal_combined():
    print_test_header("HP/MP/FP複合回復")

    user = create_test_char("勇者", hp=30, mp=10)
    target = create_test_char("戦士", hp=40, mp=15)

    item_data = {
        'id': 'I-TEST-02',
        'name': 'エリクサー',
        'consumable': True,
        'effect': {
            'type': 'heal',
            'target': 'single',
            'hp': 30,
            'mp': 10,
            'fp': -3
        }
    }

    context = {
        'room': 'test_room',
        'all_characters': [user, target]
    }

    handler = get_effect_handler('heal')
    result = handler.apply(user, target, item_data, item_data['effect'], context)

    print_result(result)
    print(f"\n対象の状態:")
    print(f"  HP: {target['hp']} / {target['maxHp']}")
    print(f"  MP: {target['mp']} / {target['maxMp']}")
    fp = next((s for s in target['states'] if s['name'] == 'FP'), None)
    print(f"  FP: {fp['value'] if fp else 0}")

# ======================================
# テスト3: 状態異常解除（全消去）
# ======================================
def test_cure_all():
    print_test_header("状態異常解除（全消去）")

    user = create_test_char("勇者")
    target = create_test_char("戦士")

    print(f"\n初期状態:")
    for state in target['states']:
        if state['name'] in ['出血', '破裂', '亀裂']:
            print(f"  {state['name']}: {state['value']}")

    item_data = {
        'id': 'I-TEST-03',
        'name': '万能解毒薬',
        'consumable': True,
        'effect': {
            'type': 'cure',
            'target': 'single',
            'remove_states': ['出血', '破裂']
        }
    }

    context = {
        'room': 'test_room',
        'all_characters': [user, target]
    }

    handler = get_effect_handler('cure')
    result = handler.apply(user, target, item_data, item_data['effect'], context)

    print_result(result)

    print(f"\n最終状態:")
    for state in target['states']:
        if state['name'] in ['出血', '破裂', '亀裂']:
            print(f"  {state['name']}: {state['value']}")

# ======================================
# テスト4: 状態異常解除（固定値）
# ======================================
def test_cure_fixed():
    print_test_header("状態異常解除（固定値）")

    user = create_test_char("勇者")
    target = create_test_char("戦士")

    print(f"\n初期状態:")
    for state in target['states']:
        if state['name'] in ['出血', '破裂']:
            print(f"  {state['name']}: {state['value']}")

    item_data = {
        'id': 'I-TEST-04',
        'name': '軽い解毒薬',
        'consumable': True,
        'effect': {
            'type': 'cure',
            'target': 'single',
            'remove_states': {
                '出血': {'mode': 'fixed', 'value': 1},
                '破裂': {'mode': 'fixed', 'value': 2}
            }
        }
    }

    context = {
        'room': 'test_room',
        'all_characters': [user, target]
    }

    handler = get_effect_handler('cure')
    result = handler.apply(user, target, item_data, item_data['effect'], context)

    print_result(result)

    print(f"\n最終状態:")
    for state in target['states']:
        if state['name'] in ['出血', '破裂']:
            print(f"  {state['name']}: {state['value']}")

# ======================================
# テスト5: 状態異常解除（割合）
# ======================================
def test_cure_percent():
    print_test_header("状態異常解除（割合）")

    user = create_test_char("勇者")
    target = create_test_char("戦士")

    print(f"\n初期状態:")
    for state in target['states']:
        if state['name'] in ['出血', '亀裂']:
            print(f"  {state['name']}: {state['value']}")

    item_data = {
        'id': 'I-TEST-05',
        'name': '中程度の解毒薬',
        'consumable': True,
        'effect': {
            'type': 'cure',
            'target': 'single',
            'remove_states': {
                '出血': {'mode': 'percent', 'value': 50},   # 3 * 50% = 1.5 → 2減少
                '亀裂': {'mode': 'percent', 'value': 75}    # 4 * 75% = 3減少
            }
        }
    }

    context = {
        'room': 'test_room',
        'all_characters': [user, target]
    }

    handler = get_effect_handler('cure')
    result = handler.apply(user, target, item_data, item_data['effect'], context)

    print_result(result)

    print(f"\n最終状態:")
    for state in target['states']:
        if state['name'] in ['出血', '亀裂']:
            print(f"  {state['name']}: {state['value']}")

# ======================================
# テスト6: バフ付与（単体）
# ======================================
def test_buff_single():
    print_test_header("バフ付与（単体）")

    user = create_test_char("勇者")
    target = create_test_char("戦士")

    item_data = {
        'id': 'I-TEST-06',
        'name': '筋力の薬',
        'consumable': True,
        'effect': {
            'type': 'buff',
            'target': 'single',
            'buff_name': '筋力強化',
            'duration': 3,
            'stat_mods': {'物理補正': 2}
        }
    }

    context = {
        'room': 'test_room',
        'all_characters': [user, target]
    }

    handler = get_effect_handler('buff')
    result = handler.apply(user, target, item_data, item_data['effect'], context)

    print_result(result)

    print(f"\nバフ一覧:")
    for buff in target.get('special_buffs', []):
        print(f"  - {buff['name']} (残り{buff['duration']}ラウンド, {buff['stat_mods']})")

# ======================================
# テスト7: 全体回復
# ======================================
def test_heal_all_allies():
    print_test_header("全体回復")

    user = create_test_char("勇者", hp=30)
    ally1 = create_test_char("戦士", hp=40, char_type='ally')
    ally2 = create_test_char("魔法使い", hp=20, char_type='ally')
    enemy = create_test_char("敵A", hp=50, char_type='enemy')

    item_data = {
        'id': 'I-TEST-07',
        'name': '全体回復薬',
        'consumable': True,
        'effect': {
            'type': 'heal',
            'target': 'all_allies',
            'hp': 15
        }
    }

    context = {
        'room': 'test_room',
        'all_characters': [user, ally1, ally2, enemy]
    }

    handler = get_effect_handler('heal')
    result = handler.apply(user, None, item_data, item_data['effect'], context)

    print_result(result)

    print(f"\n各キャラのHP:")
    print(f"  {user['name']}: {user['hp']} / {user['maxHp']}")
    print(f"  {ally1['name']}: {ally1['hp']} / {ally1['maxHp']}")
    print(f"  {ally2['name']}: {ally2['hp']} / {ally2['maxHp']}")
    print(f"  {enemy['name']}: {enemy['hp']} / {enemy['maxHp']} (敵、回復されないはず)")

# ======================================
# メイン実行
# ======================================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("Phase 4: アイテムシステムテスト")
    print("="*60)

    test_heal_single()
    test_heal_combined()
    test_cure_all()
    test_cure_fixed()
    test_cure_percent()
    test_buff_single()
    test_heal_all_allies()

    print("\n" + "="*60)
    print("全テスト完了")
    print("="*60)
