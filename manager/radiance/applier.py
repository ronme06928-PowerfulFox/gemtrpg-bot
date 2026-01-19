# manager/radiance/applier.py
"""
輝化スキルをキャラクターに適用するモジュール
"""

from manager.radiance.loader import radiance_loader


class RadianceApplier:
    """輝化スキルをキャラクターに適用"""

    def apply_radiance_skills(self, char_data, skill_ids):
        """
        輝化スキルをキャラクターに適用

        Args:
            char_data (dict): キャラクターデータ
            skill_ids (list): 輝化スキルIDのリスト

        Returns:
            dict: 更新されたキャラクターデータ
        """
        if not skill_ids:
            return char_data

        # special_buffsを初期化
        if 'special_buffs' not in char_data:
            char_data['special_buffs'] = []

        for skill_id in skill_ids:
            skill = radiance_loader.get_skill(skill_id)
            if not skill:
                print(f"[WARNING] 輝化スキル {skill_id} が見つかりません")
                continue

            effect = skill.get('effect', {})
            effect_type = effect.get('type')

            # buff効果
            if effect_type == 'buff':
                duration = effect.get('duration', skill.get('duration', -1))  # ★ スキルの duration を使用
                buff = {
                    'name': skill['name'],
                    'source': 'radiance',
                    'skill_id': skill_id,
                    'delay': 0,  # ★ 即座に発動
                    'lasting': duration,  # ★ スキルから取得
                    'is_permanent': (duration == -1),  # ★ -1なら永続
                    'stat_mods': effect.get('stat_mods', {}),
                    'description': skill.get('description', ''),
                    'flavor': skill.get('flavor', '')
                }
                char_data['special_buffs'].append(buff)
                print(f"[OK] 輝化スキル '{skill['name']}' (buff) を適用しました (lasting={duration}, permanent={duration == -1})")

            # STAT_BONUS効果（maxHp/maxMp増加など）
            elif effect_type == 'STAT_BONUS':
                stat_name = effect.get('stat')
                value = effect.get('value', 0)

                # ★ stat_modsを初期化
                stat_mods = {}

                if stat_name == 'HP':
                    # maxHpを増やす
                    current_max = int(char_data.get('maxHp', 0))
                    char_data['maxHp'] = current_max + value
                    # 現在HPも同じ量増やす（上限を超えないように）
                    char_data['hp'] = min(char_data.get('hp', 0) + value, char_data['maxHp'])
                    print(f"[OK] 輝化スキル '{skill['name']}' でHP上限+{value}（{current_max} → {char_data['maxHp']}）")
                    stat_mods['maxHp'] = value  # stat_modsに記録

                elif stat_name == 'MP':
                    # maxMpを増やす
                    current_max = int(char_data.get('maxMp', 0))
                    char_data['maxMp'] = current_max + value
                    # 現在MPも同じ量増やす（上限を超えないように）
                    char_data['mp'] = min(char_data.get('mp', 0) + value, char_data['maxMp'])
                    print(f"[OK] 輝化スキル '{skill['name']}' でMP上限+{value}（{current_max} → {char_data['maxMp']}）")
                    stat_mods['maxMp'] = value  # stat_modsに記録

                else:
                    print(f"[WARNING] 輝化スキル {skill_id} の STAT_BONUS タイプで未対応のstat: {stat_name}")
                    stat_mods[stat_name] = value  # ★ 未対応でもstat_modsには入れる

                # ★追加: STAT_BONUSタイプでもバフとして表示用にspecial_buffsに追加
                # スキルのdurationを使用（スプレッドシートから読み込まれる）
                duration = skill.get('duration', -1)
                buff = {
                    'name': skill['name'],
                    'source': 'radiance',
                    'skill_id': skill_id,
                    'delay': 0,
                    'lasting': duration,
                    'is_permanent': (duration == -1),  # ★ -1なら永続
                    'stat_mods': stat_mods,
                    'description': skill.get('description', ''),
                    'flavor': skill.get('flavor', '')
                }
                char_data['special_buffs'].append(buff)
                print(f"[OK] 輝化スキル '{skill['name']}' (STAT_BONUS) バフを追加 (lasting={duration}, permanent={duration == -1})")

            else:
                print(f"[WARNING] 輝化スキル {skill_id} は未対応の効果タイプです（type={effect_type}）")

        return char_data

    def get_stat_total(self, char_data):
        """
        バフを含めた最終ステータス補正を計算

        Args:
            char_data (dict): キャラクターデータ

        Returns:
            dict: ステータス補正の合計
        """
        total_mods = {}

        for buff in char_data.get('special_buffs', []):
            for stat, value in buff.get('stat_mods', {}).items():
                total_mods[stat] = total_mods.get(stat, 0) + value

        return total_mods


# グローバルインスタンス
radiance_applier = RadianceApplier()
