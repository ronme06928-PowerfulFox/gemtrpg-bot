"""
スキル効果適用ロジックモジュール
"""
import json
import logging
from manager.game_logic import process_skill_effects, get_status_value, apply_buff, remove_buff
from manager.room_manager import _update_char_stat, broadcast_log
from manager.battle.core import process_on_damage_buffs # ★追加
from manager.constants import DamageSource

logger = logging.getLogger(__name__)


def apply_skill_effects_bidirectional(
    room, state, username,
    winner_side, a_char, d_char, a_skill, d_skill,
    damage_val=0, suppress_actor_self_effect=False
):
    """
    マッチ双方のスキル効果を適用する

    Args:
        room: ルーム名
        state: ゲーム状態
        username: 実行ユーザー名
        winner_side: 勝者側 ('attacker' or 'defender')
        a_char: 攻撃者キャラクター
        d_char: 防御者キャラクター
        a_skill: 攻撃者スキルデータ
        d_skill: 防御者スキルデータ
        damage_val: ダメージ値（再適用用）
        suppress_actor_self_effect: 攻撃者の自己バフを抑制するか

    Returns:
        tuple: (total_bonus_damage, all_logs, custom_damage_applied)
    """
    effects_a = []
    effects_d = []

    logger.debug(f"[apply_skill_effects_bidirectional] Called: winner={winner_side}, a_char={a_char['name'] if a_char else None}, d_char={d_char['name'] if d_char else None}")

    if a_skill:
        try:
            effects_a = json.loads(a_skill.get('特記処理', '{}')).get("effects", [])
        except:
            pass

    if d_skill:
        try:
            effects_d = json.loads(d_skill.get('特記処理', '{}')).get("effects", [])
        except:
            pass

    total_bonus_dmg = 0
    custom_damage_applied = 0 # ★追加
    all_logs = []

    # 内部関数: 変更内容の即時適用
    def apply_local_changes(changes):
        nonlocal custom_damage_applied # ★移動: ここで宣言
        extra_dmg = 0

        # 重複防止のためのセット (char_id, type, name, str(value))
        applied_changes = set()

        for (char, type_, name, value) in changes:
            # APPLY_STATE の場合、重複チェックを行う
            if type_ == "APPLY_STATE":
                try:


                    # ★修正: conditionフィールドも考慮する
                    # 条件付き効果と無条件効果は別物として扱う
                    effect_obj = next((e for e in changes if e[0] == char and e[1] == type_ and e[2] == name and e[3] == value), None)
                    condition_str = ""
                    if effect_obj and len(effect_obj) > 4:
                        # changesは(char, type, name, value)のタプルだが、元のeffectからconditionを取得
                        # ここでは簡易的に、条件の有無だけをキーに含める
                        pass

                    # valueが辞書などの場合に対応するため文字列化してキーにする
                    change_key = (char.get('id'), type_, name, str(value))
                    if change_key in applied_changes:
                        logger.warning(f"[Duplicate Check] Skipping duplicate effect for {char['name']}: {name} value={value}")
                        # continue  # ★一時的に無効化: 条件付き同一効果を許可
                    applied_changes.add(change_key)
                except Exception as e:
                    logger.error(f"[Duplicate Check] Error creating key: {e}")

            if type_ == "APPLY_STATE":
                # バフ補正を除外した基礎値のみを取得
                base_curr = 0
                if name == 'HP':
                    base_curr = int(char.get('hp', 0))
                elif name == 'MP':
                    base_curr = int(char.get('mp', 0))
                else:
                    # statesから基礎値を取得
                    state = next((s for s in char.get('states', []) if s.get('name') == name), None)
                    if state:
                        try:
                            base_curr = int(state.get('value', 0))
                        except ValueError:
                            base_curr = 0

                logger.debug(f"[APPLY_STATE] {char['name']}: {name} base_current={base_curr}, adding={value}, new={base_curr + value}")
                _update_char_stat(room, char, name, base_curr + value, username=f"[{name}]")
            elif type_ == "SET_STATUS":
                _update_char_stat(room, char, name, value, username=f"[{name}]")
            elif type_ == "CUSTOM_DAMAGE":
                # ★ CUSTOM_DAMAGEを個別にHP減少させ、sourceを設定
                # nameフィールド（「破裂爆発」「亀裂崩壊」など）に応じてsourceを判定
                damage_source = None
                if name == "破裂爆発":
                    damage_source = DamageSource.RUPTURE
                elif "亀裂" in name:  # 「亀裂崩壊」など
                    damage_source = DamageSource.FISSURE
                else:
                    damage_source = DamageSource.SKILL_EFFECT

                _update_char_stat(room, char, 'HP', char['hp'] - value, username=f"[{name}]", source=damage_source)
                # ★ 追加: 内部で適用されたダメージとして集計（合計表示用）
                # nonlocal custom_damage_applied # Removed
                custom_damage_applied += value
            elif type_ == "APPLY_BUFF":
                apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
            elif type_ == "REMOVE_BUFF":
                remove_buff(char, name)
            elif type_ == "APPLY_SKILL_DAMAGE_AGAIN":
                # exta_dmg += damage_val ではなく、個別のダメージイベントとして処理する
                if damage_val > 0:
                    # 1. 直接HPを減らす
                     _update_char_stat(room, char, 'HP', char['hp'] - damage_val, username=f"[追撃]", source=DamageSource.SKILL_EFFECT)

                     # 2. 被弾時効果をトリガー (ログは統合)
                     temp_logs = []
                     buff_dmg = process_on_damage_buffs(room, char, damage_val, username, temp_logs)
                     all_logs.extend(temp_logs)

                     # 3. 合計ダメージに加算
                     # nonlocal custom_damage_applied # Removed
                     custom_damage_applied += damage_val + buff_dmg
            elif type_ == "APPLY_STATE_TO_ALL_OTHERS":
                orig_target_id = char.get("id")
                orig_target_type = char.get("type")
                for other_char in state["characters"]:
                    # 敵側（異なるタイプ）のキャラクターに適用
                    if other_char.get("type") != orig_target_type and other_char.get("id") != orig_target_id:
                        curr = get_status_value(other_char, name)
                        _update_char_stat(room, other_char, name, curr + value, username=f"[{name}]")
            elif type_ == "SET_FLAG":
                if 'flags' not in char:
                    char['flags'] = {}
                char['flags'][name] = value
        return extra_dmg

    # 内部関数: 処理実行と適用
    def run_proc_and_apply(effs, timing, actor, target, skill):
        nonlocal total_bonus_dmg

        d, l, c = process_skill_effects(effs, timing, actor, target, skill)

        # 重複防止: 攻撃者の自己バフ抑制フラグがONの場合、ターゲットが攻撃者自身である変更を除外
        final_changes = []
        if suppress_actor_self_effect and timing in ["WIN", "HIT", "LOSE", "UNOPPOSED"]:
            for change in c:
                change_target = change[0]
                # 攻撃者(a_char)への変更をスキップ
                if change_target.get('id') == a_char.get('id'):
                    continue
                final_changes.append(change)
        else:
            final_changes = c

        total_bonus_dmg += d
        all_logs.extend(l)

        # 即時適用
        dmg_val = apply_local_changes(final_changes)
        total_bonus_dmg += dmg_val

    if winner_side == 'attacker':
        # WIN -> HIT の順（勝利ボーナスをHITに乗せるため）
        logger.debug(f"[Attacker Wins] Processing attacker WIN effects")
        run_proc_and_apply(effects_a, "WIN", a_char, d_char, d_skill)
        logger.debug(f"[Attacker Wins] Processing attacker HIT effects")
        run_proc_and_apply(effects_a, "HIT", a_char, d_char, d_skill)
        logger.debug(f"[Attacker Wins] Processing defender LOSE effects")
        run_proc_and_apply(effects_d, "LOSE", d_char, a_char, a_skill)
    else:
        logger.debug(f"[Defender Wins] Processing attacker LOSE effects")
        run_proc_and_apply(effects_a, "LOSE", a_char, d_char, d_skill)
        # 防御側も WIN ->HIT に統一
        logger.debug(f"[Defender Wins] Processing defender WIN effects")
        run_proc_and_apply(effects_d, "WIN", d_char, a_char, a_skill)
        logger.debug(f"[Defender Wins] Processing defender HIT effects")
        run_proc_and_apply(effects_d, "HIT", d_char, a_char, a_skill)

    return total_bonus_dmg, all_logs, custom_damage_applied
