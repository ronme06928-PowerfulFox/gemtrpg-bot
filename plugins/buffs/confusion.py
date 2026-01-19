# plugins/buffs/confusion.py
"""
混乱バフプラグイン

2種類の混乱バフに対応：
- Bu-Confusion: 解除時MP回復なし
- Bu-ConfusionSenritsu: 解除時MP全回復
"""

from .base import BaseBuff


class ConfusionBuff(BaseBuff):
    """混乱バフプラグイン"""

    BUFF_IDS = ['Bu-02', 'Bu-03']  # Bu-Confusion, Bu-ConfusionSenritsu

    def apply(self, char, context):
        """
        混乱バフを付与

        ★ MP=0にする処理は削除（要件により）

        Args:
            char (dict): 対象キャラクター
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
            'flavor': self.flavor
        }

        # special_buffsに追加
        if 'special_buffs' not in char:
            char['special_buffs'] = []

        char['special_buffs'].append(buff_obj)

        print(f"[ConfusionBuff] Applied {self.name} to {char.get('name')} (delay={delay}, lasting={duration})")

        return {
            'success': True,
            'logs': [
                {
                    'message': f"{char.get('name', '???')} は混乱した！",
                    'type': 'debuff'
                }
            ],
            'changes': []
        }

    def on_round_end(self, char, context):
        """
        ラウンド終了時、バフが切れたらMP回復判定

        Args:
            char (dict): キャラクター
            context (dict): コンテキスト

        Returns:
            dict: {'logs': list, 'changes': list}
        """
        # restore_mp_on_endフラグをチェック
        restore_mp = self.effect.get('restore_mp_on_end', False)

        if restore_mp:
            # MP全回復（戦慄殺到版）
            max_mp = int(char.get('maxMp', 0))
            char['mp'] = max_mp

            print(f"[ConfusionBuff] {char.get('name')} recovered MP (Senritsu version)")

            return {
                'logs': [
                    {
                        'message': f"{char.get('name', '???')} は意識を取り戻した！ (MP全回復)",
                        'type': 'recovery'
                    }
                ],
                'changes': [
                    {'char_id': char.get('id'), 'stat': 'MP', 'value': max_mp}
                ]
            }
        else:
            # MP回復なし（通常版）
            print(f"[ConfusionBuff] {char.get('name')} recovered (normal version)")

            return {
                'logs': [
                    {
                        'message': f"{char.get('name', '???')} は意識を取り戻した。",
                        'type': 'recovery'
                    }
                ],
                'changes': []
            }


    @staticmethod
    def is_incapacitated(char):
        """
        行動不能（手番スキップ・ラウンド終了判定対象外）かどうか
        """
        # 混乱バフがあるか確認
        for buff in char.get('special_buffs', []):
            if buff.get('buff_id') in ['Bu-02', 'Bu-03']:  # Bu-Confusion, Bu-ConfusionSenritsu
                if buff.get('delay', 0) == 0 and buff.get('lasting', 0) > 0:
                    return True
        return False

    @staticmethod
    def can_act(char, context):
        """
        行動可能か判定（混乱中は行動不可）

        Args:
            char (dict): キャラクター
            context (dict): コンテキスト

        Returns:
            tuple: (can_act: bool, reason: str)
        """
        if ConfusionBuff.is_incapacitated(char):
            return False, '混乱中のため行動できません'

        return True, ''
