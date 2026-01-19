# plugins/buffs/base.py
"""
バフプラグインの基底クラス

すべてのバフプラグインはこのクラスを継承します。
"""


class BaseBuff:
    """バフプラグインの基底クラス"""

    # サブクラスで定義: このプラグインが処理するバフIDのリスト
    BUFF_IDS = []

    def __init__(self, buff_data):
        """
        Args:
            buff_data (dict): バフ図鑑から取得したバフデータ
                {
                    'id': 'Bu-00',
                    'name': '鋭敏',
                    'description': '...',
                    'effect': {...},
                    'default_duration': 1
                }
        """
        self.buff_id = buff_data.get('id')
        self.name = buff_data.get('name')
        self.description = buff_data.get('description')
        self.flavor = buff_data.get('flavor', '')
        self.effect = buff_data.get('effect', {})
        self.default_duration = buff_data.get('default_duration', 1)

    def apply(self, char, context):
        """
        バフ付与時の処理

        Args:
            char (dict): 対象キャラクター
            context (dict): コンテキスト
                {
                    'room': str,
                    'username': str,
                    'source': str ('item', 'radiance', 'skill'等)
                }

        Returns:
            dict: {
                'success': bool,
                'logs': list[dict],  # [{'message': str, 'type': str}]
                'changes': list[dict]  # [{'char_id': str, 'stat': str, 'value': int}]
            }
        """
        raise NotImplementedError(f"{self.__class__.__name__}.apply() must be implemented")

    def on_skill_declare(self, char, skill, context):
        """
        スキル宣言時のフック（オプション）

        バフがスキルの威力計算などに影響を与える場合に実装します。

        Args:
            char (dict): キャラクター
            skill (dict): 宣言されたスキル
            context (dict): コンテキスト

        Returns:
            dict: 変更内容
                {
                    'stat_mods': {'基礎威力': 1, '物理補正': 2, ...},
                    'skill_mods': {'range': 1, ...}  # 将来的な拡張用
                }
        """
        return {}

    def on_round_start(self, char, context):
        """
        ラウンド開始時のフック（オプション）

        Args:
            char (dict): キャラクター
            context (dict): コンテキスト

        Returns:
            dict: {
                'logs': list[dict],
                'changes': list[dict]
            }
        """
        return {'logs': [], 'changes': []}

    def on_round_end(self, char, context):
        """
        ラウンド終了時のフック（オプション）

        バフが切れた時の処理などを実装します。

        Args:
            char (dict): キャラクター
            context (dict): コンテキスト

        Returns:
            dict: {
                'logs': list[dict],
                'changes': list[dict]
            }
        """
        return {'logs': [], 'changes': []}

    def can_act(self, char, context):
        """
        行動可能か判定（オプション）

        混乱などの行動制限バフで使用します。

        Args:
            char (dict): キャラクター
            context (dict): コンテキスト

        Returns:
            tuple: (can_act: bool, reason: str)
        """
        return True, ''

    def modify_target(self, attacker, defender, context):
        """
        攻撃対象の変更（オプション）

        挑発などのターゲット強制変更バフで使用します。

        Args:
            attacker (dict): 攻撃者
            defender (dict): 本来の防御者
            context (dict): コンテキスト

        Returns:
            dict: 変更後の防御者（変更なしの場合はdefenderをそのまま返す）
        """
        return defender
