# plugins/buffs/dodge_lock.py
"""
再回避ロックバフプラグイン

回避成功時に付与され、そのラウンドは行動済みでも攻撃対象に選択されたら
行動可能だが、記録されたIDの回避スキルしか使用できない
"""

from .base import BaseBuff


class DodgeLockBuff(BaseBuff):
    """再回避ロックバフプラグイン"""

    BUFF_IDS = ['Bu-05']

    def apply(self, char, context):
        """
        再回避ロックバフを付与

        Args:
            char (dict): 対象キャラクター
            context (dict): コンテキスト
                {
                    'room': str,
                    'source': str,
                    'skill_id': str  # ★ 記録する回避スキルID
                }

        Returns:
            dict: 適用結果
        """
        duration = self.default_duration
        source = context.get('source', 'unknown')
        delay = context.get('delay', 0)
        skill_id = context.get('skill_id')  # ★ 回避スキルIDを取得

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
            'skill_id': skill_id  # ★ 回避スキルIDを保存
        }

        # special_buffsに追加
        if 'special_buffs' not in char:
            char['special_buffs'] = []

        char['special_buffs'].append(buff_obj)

        print(f"[DodgeLockBuff] Applied {self.name} to {char.get('name')} (skill_id={skill_id})")

        return {
            'success': True,
            'logs': [
                {
                    'message': f"{char.get('name', '???')} は再回避可能になった！",
                    'type': 'buff'
                }
            ],
            'changes': []
        }

    @staticmethod
    def has_re_evasion(char):
        """
        再回避ロックバフを持っているか確認

        Args:
            char (dict): キャラクター

        Returns:
            bool: 再回避可能かどうか
        """
        if 'special_buffs' not in char:
            return False

        for buff in char['special_buffs']:
            # IDまたは名前で判定
            is_target = False
            if buff.get('buff_id') == 'Bu-05':
                is_target = True
            elif buff.get('name') == '再回避ロック':
                is_target = True

            if is_target:
                # delayが0で、lastingが残っている場合のみ有効
                if buff.get('delay', 0) == 0 and buff.get('lasting', 0) > 0:
                    return True

        return False

    @staticmethod
    def get_locked_skill_id(char):
        """
        再回避ロック中の使用可能スキルIDを取得

        Args:
            char (dict): キャラクター

        Returns:
            str or None: 使用可能な回避スキルID
        """
        if 'special_buffs' not in char:
            return None

        for buff in char['special_buffs']:
            # IDまたは名前で判定（後方互換性と堅牢性のため）
            is_target = False
            if buff.get('buff_id') == 'Bu-05':
                is_target = True
            elif buff.get('name') == '再回避ロック':
                is_target = True

            if is_target:
                if buff.get('delay', 0) == 0 and buff.get('lasting', 0) > 0:
                    return buff.get('skill_id')

        return None
