
from .base import BaseBuff
from plugins.burst import BurstEffect
from manager.status_manager import get_status_value

class TimeBombBuff(BaseBuff):
    """時限式破裂爆発バフプラグイン"""

    # 仮のID。必要に応じて変更してください。
    BUFF_IDS = ['Bu-07']

    def on_delay_zero(self, char, context):
        """
        ディレイが0になった瞬間に発動する処理

        Args:
            char (dict): キャラクターデータ
            context (dict): コンテキスト {'room': room_name}

        Returns:
            dict: {
                'logs': list[dict],
                'changes': list[dict]
            }
        """
        room = context.get('room')
        if not room:
            return {'logs': [], 'changes': []}

        logs = []
        changes = []

        # 破裂ステータスがあるか確認
        current_burst = get_status_value(char, "破裂")
        if current_burst > 0:
            # BurstEffectをインスタンス化して適用
            # BurstEffect.apply は (actor, target, params, context) を取る
            # ここでは actor=char, target=char (自分自身に発動)

            # BurstEffectは通常スキルから呼ばれるが、ここではバフから自動発動
            # paramsに 'rupture_remainder_ratio' などが必要だが、
            # デフォルト動作（全消費？）または現状維持かを確認。
            # 破裂の仕様: apply内で "rupture_remainder_ratio" を params または context から取得
            # 指定がない場合は 0.0 (全消費) になるはず。

            effect_plugin = BurstEffect()

            # コンテキストにトリガー情報を追加
            effect_context = context.copy()
            effect_context['trigger_ratio'] = 0.0 # デフォルト: 全消費してダメージ

            # エフェクト適用
            # paramsは空で良い（特別な補正がない限り）
            effect_changes, effect_logs = effect_plugin.apply(char, char, {}, effect_context)

            # ログを整形 (文字列リストが返ってくる場合と、dictリストの場合があるため注意)
            # BurstEffect.apply は (changes, logs) を返す。
            # logs は文字列のリスト ["xxx", "yyy"]

            for log_msg in effect_logs:
                logs.append({'message': log_msg, 'type': 'damage'})

            changes.extend(effect_changes)

            # 追加ログ
            logs.append({'message': f"【時限発動】{char['name']} に溜まった破裂が起爆した！", 'type': 'state-change'})

        return {
            'logs': logs,
            'changes': changes
        }
