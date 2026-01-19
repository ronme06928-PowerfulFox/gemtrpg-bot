# plugins/items/heal.py
"""
HP/MP/FP回復効果
"""

from .base import BaseItemEffect

class HealEffect(BaseItemEffect):
    """HP/MP/FP回復効果"""

    def apply(self, user_char, target_char, item_data, params, context):
        """
        回復効果を適用

        params の想定形式:
        {
            "type": "heal",
            "target": "single" or "all_allies" or "all_enemies",
            "hp": 20,      # HP回復量（正の値で回復、負の値でダメージ）
            "mp": 10,      # MP回復量
            "fp": -5       # FP変動量
        }
        """
        changes = []
        logs = []

        # 対象キャラクターのリストを作成
        target_type = params.get('target', 'single')
        targets = []

        if target_type == 'single':
            targets = [target_char] if target_char else []
        elif target_type == 'all_allies':
            user_type = user_char.get('type', 'ally')
            targets = [c for c in context['all_characters'] if c.get('type') == user_type and c.get('hp', 0) > 0]
        elif target_type == 'all_enemies':
            user_type = user_char.get('type', 'ally')
            enemy_type = 'enemy' if user_type == 'ally' else 'ally'
            targets = [c for c in context['all_characters'] if c.get('type') == enemy_type and c.get('hp', 0) > 0]

        if not targets:
            return {
                'success': False,
                'changes': [],
                'logs': [{'message': '対象が見つかりません', 'type': 'error'}],
                'consumed': False
            }

        # 各対象に効果を適用
        for target in targets:
            target_name = target.get('name', '???')

            # HP回復
            hp_delta = params.get('hp', 0)
            if hp_delta != 0:
                old_hp = target.get('hp', 0)
                max_hp = target.get('maxHp', 0)
                new_hp = max(0, min(max_hp, old_hp + hp_delta))
                actual_delta = new_hp - old_hp

                if actual_delta != 0:
                    target['hp'] = new_hp
                    changes.append({
                        'id': target.get('id'),
                        'field': 'hp',
                        'old': old_hp,
                        'new': new_hp,
                        'delta': actual_delta
                    })

                    if actual_delta > 0:
                        logs.append({'message': f'{target_name} のHPが {actual_delta} 回復した！ ({old_hp} → {new_hp})', 'type': 'info'})
                    else:
                        logs.append({'message': f'{target_name} に {abs(actual_delta)} のダメージ！ ({old_hp} → {new_hp})', 'type': 'damage'})

            # MP回復
            mp_delta = params.get('mp', 0)
            if mp_delta != 0:
                old_mp = target.get('mp', 0)
                max_mp = target.get('maxMp', 0)
                new_mp = max(0, min(max_mp, old_mp + mp_delta))
                actual_delta = new_mp - old_mp

                if actual_delta != 0:
                    target['mp'] = new_mp
                    changes.append({
                        'id': target.get('id'),
                        'field': 'mp',
                        'old': old_mp,
                        'new': new_mp,
                        'delta': actual_delta
                    })

                    if actual_delta > 0:
                        logs.append({'message': f'{target_name} のMPが {actual_delta} 回復した！ ({old_mp} → {new_mp})', 'type': 'info'})
                    else:
                        logs.append({'message': f'{target_name} のMPが {abs(actual_delta)} 減少した！ ({old_mp} → {new_mp})', 'type': 'info'})

            # FP変動
            fp_delta = params.get('fp', 0)
            if fp_delta != 0:
                states = target.get('states', [])
                fp_state = next((s for s in states if s.get('name') == 'FP'), None)

                if fp_state:
                    old_fp = fp_state.get('value', 0)
                    new_fp = max(0, min(15, old_fp + fp_delta))
                    actual_delta = new_fp - old_fp

                    if actual_delta != 0:
                        fp_state['value'] = new_fp
                        changes.append({
                            'id': target.get('id'),
                            'field': 'FP',
                            'old': old_fp,
                            'new': new_fp,
                            'delta': actual_delta
                        })

                        if actual_delta > 0:
                            logs.append({'message': f'{target_name} のFPが {actual_delta} 増加した！ ({old_fp} → {new_fp})', 'type': 'info'})
                        else:
                            logs.append({'message': f'{target_name} のFPが {abs(actual_delta)} 減少した！ ({old_fp} → {new_fp})', 'type': 'info'})

        return {
            'success': True,
            'changes': changes,
            'logs': logs,
            'consumed': item_data.get('consumable', True)
        }
