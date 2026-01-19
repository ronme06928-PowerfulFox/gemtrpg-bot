# plugins/items/buff.py
"""
バフ付与効果
"""

from .base import BaseItemEffect

class BuffEffect(BaseItemEffect):
    """バフ付与効果"""

    def apply(self, user_char, target_char, item_data, effect_params, context):
        """
        バフ効果を適用

        Args:
            user_char (dict): 使用者
            target_char (dict): 対象キャラクター
            item_data (dict): アイテムデータ
            effect_params (dict): 効果パラメータ {'buff_id': 'Bu-00'}
            context (dict): コンテキスト

        Returns:
            dict: 適用結果
        """
        buff_id = effect_params.get('buff_id')
        if not buff_id:
            return {
                'success': False,
                'changes': [],
                'logs': [{'message': 'バフIDが指定されていません', 'type': 'error'}],
                'consumed': False
            }

        # ★ バフ図鑑からバフ定義を取得
        from manager.buffs.loader import buff_catalog_loader
        buff_data = buff_catalog_loader.get_buff(buff_id)

        if not buff_data:
            return {
                'success': False,
                'changes': [],
                'logs': [{'message': f'バフ {buff_id} が見つかりません', 'type': 'error'}],
                'consumed': False
            }

        # ★ バフプラグインレジストリからハンドラを取得
        from plugins.buffs.registry import buff_registry
        handler_class = buff_registry.get_handler(buff_id)

        if handler_class:
            # プラグイン経由でバフを適用
            print(f"[BuffEffect] Using plugin {handler_class.__name__} for {buff_id}")

            buff_instance = handler_class(buff_data)
            plugin_context = {
                'room': context.get('room'),
                'username': context.get('username', user_char.get('name')),
                'source': 'item'
            }

            result = buff_instance.apply(target_char, plugin_context)

            # consumed フラグを追加
            result['consumed'] = True
            return result

        else:
            # ★ フォールバック: プラグインがない場合、従来の方式
            print(f"[BuffEffect] No plugin for {buff_id}, using legacy method")

            # special_buffsに直接追加（レガシー方式）
            if 'special_buffs' not in target_char:
                target_char['special_buffs'] = []

            buff_obj = {
                'name': buff_data.get('name'),
                'source': 'item',
                'buff_id': buff_id,
                'delay': 0,
                'lasting': buff_data.get('default_duration', 1),
                'is_permanent': False,
                'description': buff_data.get('description'),
                'flavor': buff_data.get('flavor', '')
            }

            # effectからstat_modsを構築
            effect = buff_data.get('effect', {})
            if effect.get('type') == 'stat_mod':
                stat = effect.get('stat')
                value = effect.get('value')
                buff_obj['stat_mods'] = {stat: value}

            target_char['special_buffs'].append(buff_obj)

            return {
                'success': True,
                'changes': [],
                'logs': [
                    {
                        'message': f"{target_char.get('name', '???')} に [{buff_data.get('name')}] が付与された！",
                        'type': 'buff'
                    }
                ],
                'consumed': True
            }
