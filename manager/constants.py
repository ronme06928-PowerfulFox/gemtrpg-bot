"""
定数定義モジュール

ゲームシステム全体で使用される定数を定義する。
"""

class DamageSource:
    """
    ダメージ発生源を識別するための定数クラス。
    フローティングテキストの色分けやログ表示に使用される。
    """
    # マッチ関連
    MATCH_LOSS = "match_loss"          # 通常マッチでの敗北
    ONE_SIDED = "one_sided"            # 一方攻撃

    # 状態異常
    BLEED = "bleed"                    # 出血（ラウンド終了時）
    BLEED_FLOOD = "bleed_flood"        # 出血氾濫（スキル効果）
    THORNS = "thorns"                  # 荊棘の自傷ダメージ

    # スキル効果
    RUPTURE = "rupture"                # 破裂爆発
    FISSURE = "fissure"                # 亀裂崩壊

    # その他
    GENERIC = "generic"                # 汎用（デフォルト）
    SKILL_EFFECT = "skill_effect"      # スキル効果全般

    @classmethod
    def get_display_name(cls, source):
        """発生源の表示名を取得"""
        display_names = {
            cls.MATCH_LOSS: "マッチ敗北",
            cls.ONE_SIDED: "一方攻撃",
            cls.BLEED: "出血",
            cls.BLEED_FLOOD: "出血氾濫",
            cls.THORNS: "荊棘",
            cls.RUPTURE: "破裂",
            cls.FISSURE: "亀裂崩壊",
            cls.GENERIC: "ダメージ",
            cls.SKILL_EFFECT: "スキル効果",
        }
        return display_names.get(source, source)
