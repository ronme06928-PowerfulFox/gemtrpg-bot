# plugins/items/cure.py
"""
状態異常解除効果
"""

from .base import BaseItemEffect
import math

class CureEffect(BaseItemEffect):
    """状態異常解除効果"""

    def apply(self, user_char, target_char, item_data, params, context):
        """
        状態異常解除効果を適用

        params の想定形式（複数パターン対応）:

        パターン1: 全消去
        {
            "type": "cure",
            "target": "single",
            "remove_states": ["出血", "破裂"],
            "mode": "all"  # デフォルト（省略可）
        }

        パターン2: 固定値で減少
        {
            "type": "cure",
            "target": "single",
            "remove_states": {
                "出血": {"mode": "fixed", "value": 2},
                "破裂": {"mode": "fixed", "value": 1}
            }
        }

        パターン3: 割合で減少
        {
            "type": "cure",
            "target": "single",
            "remove_states": {
                "出血": {"mode": "percent", "value": 50},  # 50%減少
                "亀裂": {"mode": "percent", "value": 100}  # 100%=全消去
            }
        }

        パターン4: 混在
        {
            "type": "cure",
            "target": "all_allies",
            "remove_states": {
                "出血": {"mode": "all"},           # 全消去
                "破裂": {"mode": "fixed", "value": 1},  # 1減少
                "亀裂": {"mode": "percent", "value": 50}  # 50%減少
            }
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
        elif target_type == 'all':
            targets = [c for c in context['all_characters'] if c.get('hp', 0) > 0]

        if not targets:
            return {
                'success': False,
                'changes': [],
                'logs': [{'message': '対象が見つかりません', 'type': 'error'}],
                'consumed': False
            }

        # 解除する状態異常のリスト/辞書を取得
        remove_states = params.get('remove_states', [])

        if not remove_states:
            return {
                'success': False,
                'changes': [],
                'logs': [{'message': '解除する状態異常が指定されていません', 'type': 'error'}],
                'consumed': False
            }

        # 各対象に効果を適用
        for target in targets:
            target_name = target.get('name', '???')
            states = target.get('states', [])
            removed_any = False

            # リスト形式（全消去モード）の場合
            if isinstance(remove_states, list):
                for state_name in remove_states:
                    result = self._remove_state(target, states, state_name, {'mode': 'all'})
                    if result:
                        changes.append(result['change'])
                        logs.append(result['log'])
                        removed_any = True

            # 辞書形式（詳細制御モード）の場合
            elif isinstance(remove_states, dict):
                for state_name, state_config in remove_states.items():
                    result = self._remove_state(target, states, state_name, state_config)
                    if result:
                        changes.append(result['change'])
                        logs.append(result['log'])
                        removed_any = True

            if not removed_any:
                logs.append({'message': f'{target_name} には解除する状態異常がありませんでした。', 'type': 'info'})

        return {
            'success': True,
            'changes': changes,
            'logs': logs,
            'consumed': item_data.get('consumable', True)
        }

    def _remove_state(self, target, states, state_name, config):
        """
        単一の状態異常を処理

        Args:
            target: 対象キャラクター
            states: 状態異常リスト
            state_name: 状態異常名
            config: 設定（mode, valueを含む辞書）

        Returns:
            dict or None: {'change': {...}, 'log': {...}} or None
        """
        state = next((s for s in states if s.get('name') == state_name), None)

        if not state or state.get('value', 0) == 0:
            return None

        old_value = state.get('value', 0)
        mode = config.get('mode', 'all')
        target_name = target.get('name', '???')

        new_value = 0

        if mode == 'all':
            # 全消去
            new_value = 0
        elif mode == 'fixed':
            # 固定値減少
            reduction = config.get('value', 0)
            new_value = max(0, old_value - reduction)
        elif mode == 'percent':
            # 割合減少
            percent = config.get('value', 0)
            reduction = math.ceil(abs(old_value) * percent / 100)
            if old_value > 0:
                new_value = max(0, old_value - reduction)
            else:
                new_value = min(0, old_value + reduction)

        if new_value == old_value:
            return None

        state['value'] = new_value
        delta = new_value - old_value

        # ログメッセージを生成
        if new_value == 0:
            log_message = f'{target_name} の {state_name} が解除された！'
        else:
            log_message = f'{target_name} の {state_name} が {abs(delta)} 減少した！ ({old_value} → {new_value})'

        return {
            'change': {
                'id': target.get('id'),
                'field': state_name,
                'old': old_value,
                'new': new_value,
                'delta': delta
            },
            'log': {'message': log_message, 'type': 'info'}
        }
