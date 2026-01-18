"""
スキル効果適用ロジックモジュール
"""
import json
from manager.game_logic import process_skill_effects, get_status_value, apply_buff, remove_buff
from manager.room_manager import _update_char_stat, broadcast_log


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
        tuple: (total_bonus_damage, all_logs)
    """
    effects_a = []
    effects_d = []

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
    all_logs = []

    # 内部関数: 変更内容の即時適用
    def apply_local_changes(changes):
        extra_dmg = 0
        for (char, type_, name, value) in changes:
            if type_ == "APPLY_STATE":
                curr = get_status_value(char, name)
                _update_char_stat(room, char, name, curr + value, username=f"[{name}]")
            elif type_ == "SET_STATUS":
                _update_char_stat(room, char, name, value, username=f"[{name}]")
            elif type_ == "CUSTOM_DAMAGE":
                extra_dmg += value
            elif type_ == "APPLY_BUFF":
                apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
            elif type_ == "REMOVE_BUFF":
                remove_buff(char, name)
            elif type_ == "APPLY_SKILL_DAMAGE_AGAIN":
                extra_dmg += damage_val
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
        run_proc_and_apply(effects_a, "WIN", a_char, d_char, d_skill)
        run_proc_and_apply(effects_a, "HIT", a_char, d_char, d_skill)
        run_proc_and_apply(effects_d, "LOSE", d_char, a_char, a_skill)
    else:
        run_proc_and_apply(effects_a, "LOSE", a_char, d_char, d_skill)
        # 防御側も WIN ->HIT に統一
        run_proc_and_apply(effects_d, "WIN", d_char, a_char, a_skill)
        run_proc_and_apply(effects_d, "HIT", d_char, a_char, a_skill)

    return total_bonus_dmg, all_logs
