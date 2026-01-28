from .base import BaseBuff

class ImplosionBuff(BaseBuff):
    """
    Bu-09 爆縮:
    スキルでダメージを与える時、ダメージ+5。
    回数制限あり（外部でカウント管理）。
    """
    BUFF_IDS = ['Bu-09']
    id = "Bu-09"
    name = "爆縮"
    description = "与ダメージ+5 (8回まで)"
    flavor = "圧縮されたエネルギーが、攻撃の瞬間に弾け飛ぶ。"

    @classmethod
    def on_hit_damage_calculation(cls, actor, target, damage_val, context=None):
        # 攻撃者が自分である場合のみ発動
        # バフデータから現在のカウントを取得
        buff_data = None
        if actor and 'special_buffs' in actor:
            buff_data = next((b for b in actor['special_buffs'] if b['name'] == cls.name), None)

        if not buff_data:
            return damage_val, [] # バフが見つからない

        current_count = buff_data.get('count', 0)

        # カウントが残っている場合のみ発動
        if current_count > 0:
            # カウント消費
            buff_data['count'] = current_count - 1

            # ダメージ加算 (+5)
            new_damage = damage_val + 5

            # ログ用メッセージ
            log_message = f"[{cls.name}] 効果発動: ダメージ+5 (残{buff_data['count']}回)"

            return new_damage, [log_message]

        return damage_val, []
