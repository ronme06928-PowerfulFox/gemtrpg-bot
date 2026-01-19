# plugins/buffs/provoke.py
"""
挑発バフプラグイン

攻撃対象を挑発者に強制変更する
"""

from .base import BaseBuff


class ProvokeBuff(BaseBuff):
    """挑発バフプラグイン"""

    BUFF_IDS = ['Bu-Provoke', 'Bu-01']

    def apply(self, char, context):
        """
        挑発バフを付与

        Args:
            char (dict): 挑発者（バフを受けるキャラ）
            context (dict): コンテキスト

        Returns:
            dict: 適用結果
        """
        duration = self.default_duration
        source = context.get('source', 'unknown')
        delay = context.get('delay', 0)

        # バフオブジェクトを構築
        buff_obj = {
            'name': self.name,
            'source': source,
            'buff_id': self.buff_id,
            'delay': delay,
            'lasting': duration,
            'is_permanent': False,
            'description': self.description,
            'flavor': self.flavor,
            # 挑発者のIDを記録
            'provoker_id': char.get('id')
        }

        # special_buffsに追加
        if 'special_buffs' not in char:
            char['special_buffs'] = []

        char['special_buffs'].append(buff_obj)

        print(f"[ProvokeBuff] Applied {self.name} to {char.get('name')} (delay={delay}, lasting={duration})")

        return {
            'success': True,
            'logs': [
                {
                    'message': f"{char.get('name', '???')} に [{self.name}] が付与された！",
                    'type': 'buff'
                }
            ],
            'changes': []
        }

    def modify_target(self, attacker, defender, context):
        """
        攻撃対象を挑発者に変更

        Args:
            attacker (dict): 攻撃者
            defender (dict): 本来の防御者
            context (dict): コンテキスト

        Returns:
            dict: 変更後の防御者
        """
        # 全キャラクターから挑発バフを持つキャラを探す
        all_chars = context.get('all_characters', [])

        for char in all_chars:
            for buff in char.get('special_buffs', []):
                if buff.get('buff_id') == 'Bu-Provoke':
                    # delayが0で、lastingが残っている場合のみ有効
                    if buff.get('delay', 0) == 0 and buff.get('lasting', 0) > 0:
                        # 挑発者が敵側かチェック
                        attacker_type = attacker.get('type', 'ally')
                        provoker_type = char.get('type', 'ally')

                        if attacker_type != provoker_type:
                            print(f"[ProvokeBuff] Target changed: {defender.get('name')} → {char.get('name')} (by provoke)")
                            return char

        return defender
