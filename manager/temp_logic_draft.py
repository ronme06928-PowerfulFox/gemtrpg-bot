def calculate_skill_preview(actor_char, target_char, skill_data, rule_data=None, custom_skill_name=None, senritsu_max_apply=0):
    """
    スキルの威力、コマンド、補正情報のプレビューデータを計算する。
    Duel/Wide Matchの両方で共通して使用する。
    """
    if not target_char:
        return {
            "final_command": "エラー: マッチには「対象」が必要です",
            "min_damage": 0, "max_damage": 0, "error": True
        }

    # 1. 威力ボーナスの計算
    power_bonus = 0
    if rule_data:
        power_bonus_data = rule_data.get('power_bonus') if isinstance(rule_data, dict) and 'power_bonus' in rule_data else rule_data
        power_bonus = _calculate_bonus_from_rules(power_bonus_data if isinstance(power_bonus_data, list) else [], actor_char, target_char) # Note: _calculate_bonus_from_rules usage might need adjustment if not accessible or args differ

    # Helper function `calculate_power_bonus` is not imported, but `_calculate_bonus_from_rules` exists in this file.
    # In socket_battle.py it calls `calculate_power_bonus`.
    # `calculate_power_bonus` in socket_battle seems to be a wrapper related to rule loading,
    # but here we assume logic is checking rules.
    # Actually socket_battle `calculate_power_bonus` is imported from `manager.game_logic`.
    # Wait, `calculate_power_bonus` IS in `manager/game_logic.py`?
    # The view_file output didn't show it explicitly but I should check if I missed it or if it needs to be exported/used.
    # Lines 87-100 show `calculate_buff_power_bonus`.
    # I should use `calculate_buff_power_bonus` available in this file.

    # Let's verify `calculate_power_bonus` existence.
    # _calculate_bonus_from_rules is defined at line 46.

    # 2. バフによる威力ボーナス
    buff_bonus = calculate_buff_power_bonus(actor_char, target_char, skill_data)
    total_modifier = power_bonus + buff_bonus

    # 3. 基礎コマンドの解決
    base_command = skill_data.get('チャットパレット', '')
    resolved_command = resolve_placeholders(base_command, actor_char)
    skill_id = skill_data.get('id', '??')
    if custom_skill_name:
        resolved_command = re.sub(r'【.*?】', f'【{skill_id} {custom_skill_name}】', resolved_command)

    # 4. 基礎威力の計算
    base_power = 0
    try: base_power = int(skill_data.get('基礎威力', 0))
    except (ValueError, TypeError): base_power = 0

    base_power_buff_mod = get_buff_stat_mod(actor_char, '基礎威力')
    base_power += base_power_buff_mod

    # 5. ダイス威力の解析と戦慄適用
    dice_roll_str = skill_data.get('ダイス威力', "")
    dice_min = 0; dice_max = 0
    original_num_faces = 0
    senritsu_dice_reduction = 0

    dice_match = re.search(r'([+-]?)(\d+)d(\d+)', dice_roll_str)
    if dice_match:
        try:
            sign = dice_match.group(1)
            is_negative_dice = (sign == '-')
            num_dice = int(dice_match.group(2))
            original_num_faces = int(dice_match.group(3))
            num_faces = original_num_faces

            if senritsu_max_apply > 0 and num_faces > 1:
                max_reduction = num_faces - 1
                senritsu_dice_reduction = min(senritsu_max_apply, max_reduction)
                num_faces = num_faces - senritsu_dice_reduction

            if is_negative_dice:
                dice_min = -(num_dice * num_faces)
                dice_max = -num_dice
            else:
                dice_min = num_dice
                dice_max = num_dice * num_faces
        except Exception: pass

    # 6. 物理/魔法補正の適用
    phys_correction = get_status_value(actor_char, '物理補正')
    mag_correction = get_status_value(actor_char, '魔法補正')
    phys_correction_details = get_buff_stat_mod_details(actor_char, '物理補正')
    mag_correction_details = get_buff_stat_mod_details(actor_char, '魔法補正')

    correction_min = 0; correction_max = 0
    correction_details = []

    if '{物理補正}' in base_command:
        correction_max = phys_correction
        if phys_correction >= 1: correction_min = 1
        correction_details = phys_correction_details
    elif '{魔法補正}' in base_command:
        correction_max = mag_correction
        if mag_correction >= 1: correction_min = 1
        correction_details = mag_correction_details

    # 7. 最終ダメージレンジ
    min_damage = base_power + dice_min + correction_min + total_modifier
    max_damage = base_power + dice_max + correction_max + total_modifier

    # 8. コマンド文字列の最終構築
    final_command = resolved_command

    # 基礎威力補正の反映
    if base_power_buff_mod != 0:
        try:
            original_base = int(skill_data.get('基礎威力', 0))
            if original_base > 0 and f"{original_base}+" in final_command:
                final_command = final_command.replace(f"{original_base}+", f"{base_power}+", 1)
            elif base_power > 0 and original_base == 0:
                final_command = f"{base_power}+" + final_command
        except Exception: pass

    # 戦慄反映
    if senritsu_dice_reduction > 0 and original_num_faces > 0:
        reduced_faces = original_num_faces - senritsu_dice_reduction
        def replace_first_dice(m):
            return f"{m.group(1)}{m.group(2)}d{reduced_faces}"
        final_command = re.sub(r'([+-]?)(\d+)d' + str(original_num_faces), replace_first_dice, final_command, count=1)

    # 補正値(total_modifier)反映
    if total_modifier > 0:
        if ' 【' in final_command: final_command = final_command.replace(' 【', f"+{total_modifier} 【")
        else: final_command += f"+{total_modifier}"
    elif total_modifier < 0:
        if ' 【' in final_command: final_command = final_command.replace(' 【', f"{total_modifier} 【")
        else: final_command += f"{total_modifier}"

    return {
        "final_command": final_command,
        "min_damage": min_damage,
        "max_damage": max_damage,
        "damage_range_text": f"Range: {min_damage} ~ {max_damage}",
        "correction_details": correction_details,
        "senritsu_dice_reduction": senritsu_dice_reduction,
        "skill_details": {
             "base_power_mod": base_power_buff_mod,
             "name": skill_data.get('name', ''),
             "effect": skill_data.get('説明', '')
        },
        "power_breakdown": {
             "base_power_mod": base_power_buff_mod,
             "additional_power": total_modifier
        },
        "error": False
    }
