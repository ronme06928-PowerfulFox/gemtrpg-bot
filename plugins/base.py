# plugins/base.py
class BaseEffect:
    def apply(self, actor, target, params, context):
        """
        効果を適用する
        :param actor: 実行者キャラデータ
        :param target: 対象キャラデータ
        :param params: JSONの "CUSTOM_EFFECT" オブジェクト全体
        :param context: { "registry": ..., "utils": ... } などの共有データ
        :return: (changes, logs)
        """
        return [], []