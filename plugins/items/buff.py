# plugins/items/buff.py
"""
バフ付与効果
"""

from .base import BaseItemEffect

class BuffEffect(BaseItemEffect):
    """バフ付与効果"""

    def apply(self, user_char, target_char, item_data, params, context):
        """
        バフ付与効果を適用

        params の想定形式:
        {
            "type": "buff",
            "target": "single" or "all_allies",
            "buff_name": "攻撃力上昇",
            "duration": 3,
            "stat_mods": {"物理補正": 2, "魔法補正": 1}
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

        # ★ バフID参照方式
        buff_id = params.get('buff_id')
        if not buff_id:
            # 後方互換性: buff_nameもサポート
            buff_id = params.get('buff_name')

        if not buff_id:
            return {
                'success': False,
                'changes': [],
                'logs': [{'message': 'バフIDが指定されていません', 'type': 'error'}],
                'consumed': False
            }

        # バフ図鑑からバフ情報を取得
        from manager.buffs.loader import buff_catalog_loader
        buff_data = buff_catalog_loader.get_buff(buff_id)

        if not buff_data:
            return {
                'success': False,
                'changes': [],
                'logs': [{'message': f'バフ {buff_id} が見つかりません', 'type': 'error'}],
                'consumed': False
            }

        # バフ名を取得
        buff_name = buff_data.get('name', buff_id)

        # パラメータから持続時間を取得（指定がなければバフ図鑑のデフォルトを使用）
        duration = params.get('duration')
        if duration is None:
            duration = buff_data.get('default_duration', 1)

        # ディレイ
        delay = params.get('delay', 0)

        # ステータス補正
        stat_mods = buff_data.get('effect', {})
        if stat_mods.get('type') == 'stat_mod':
            stat_mods = {stat_mods.get('stat'): stat_mods.get('value', 0)}
        else:
            # paramsでstat_modsが指定されている場合はそちらを優先
            stat_mods = params.get('stat_mods', stat_mods)

        # 各対象にバフを付与
        for target in targets:
            target_name = target.get('name', '???')

            # special_buffs の初期化
            if 'special_buffs' not in target:
                target['special_buffs'] = []

            # 既存の同名バフを削除（スタックしない）
            target['special_buffs'] = [b for b in target['special_buffs'] if b.get('name') != buff_name]

            # 新しいバフを追加
            new_buff = {
                'name': buff_name,
                'source': 'item',
                'item_id': item_data.get('id', ''),
                'delay': delay,
                'lasting': duration,
                'is_permanent': False,
                'stat_mods': stat_mods,
                'description': buff_data.get('description', ''),
                'flavor': buff_data.get('flavor', '')
            }

            target['special_buffs'].append(new_buff)

            changes.append({
                'id': target.get('id'),
                'field': 'special_buffs',
                'old': None,
                'new': buff_name,
                'delta': None
            })

            # ログメッセージ
            if duration > 0:
                logs.append({'message': f'{target_name} に {buff_name} が付与された！ (残り{duration}ラウンド)', 'type': 'buff'})
            else:
                logs.append({'message': f'{target_name} に {buff_name} が付与された！ (永続)', 'type': 'buff'})

        return {
            'success': True,
            'changes': changes,
            'logs': logs,
            'consumed': item_data.get('consumable', True)
        }
