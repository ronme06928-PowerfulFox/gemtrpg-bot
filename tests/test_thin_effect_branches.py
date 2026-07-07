# tests/test_thin_effect_branches.py
"""
process_skill_effects の薄い分岐（DAMAGE_BONUS / MODIFY_ROLL / FORCE_UNOPPOSED /
MODIFY_FINAL_POWER / DRAIN_HP）の特性化テスト。

計画書 29（game_logic.py 分割）Phase 0 で追加。分割前後で入出力が変わらないことを
固定するのが目的のため、期待値は現行実装の観測値に一致させている。
"""
from manager.game_logic import process_skill_effects


class TestDamageBonus:
    def test_positive_value_adds_bonus_damage(self, sample_actor, sample_target):
        effects = [{"timing": "HIT", "type": "DAMAGE_BONUS", "value": 4}]

        bonus, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        assert bonus == 4
        assert any("[追加ダメージ +4]" in log for log in logs)
        assert changes == []

    def test_zero_value_is_ignored(self, sample_actor, sample_target):
        effects = [{"timing": "HIT", "type": "DAMAGE_BONUS", "value": 0}]

        bonus, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        assert bonus == 0
        assert not any("追加ダメージ" in log for log in logs)


class TestModifyRoll:
    def test_positive_value_adds_bonus(self, sample_actor, sample_target):
        effects = [{"timing": "HIT", "type": "MODIFY_ROLL", "value": 3}]

        bonus, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        assert bonus == 3
        assert any("[ロール補正 +3]" in log for log in logs)

    def test_negative_value_subtracts(self, sample_actor, sample_target):
        effects = [{"timing": "HIT", "type": "MODIFY_ROLL", "value": -2}]

        bonus, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        assert bonus == -2
        assert any("[ロール補正 -2]" in log for log in logs)

    def test_zero_value_is_ignored(self, sample_actor, sample_target):
        effects = [{"timing": "HIT", "type": "MODIFY_ROLL", "value": 0}]

        bonus, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        assert bonus == 0
        assert not any("ロール補正" in log for log in logs)


class TestForceUnopposed:
    def test_appends_change_without_log(self, sample_actor, sample_target):
        effects = [{"timing": "PRE_MATCH", "type": "FORCE_UNOPPOSED"}]

        bonus, logs, changes = process_skill_effects(
            effects, "PRE_MATCH", sample_actor, sample_target
        )

        force_changes = [c for c in changes if c[1] == "FORCE_UNOPPOSED"]
        assert len(force_changes) == 1
        char, ctype, name, value = force_changes[0]
        assert char is sample_target
        assert name == "None"
        assert value == 0


class TestModifyFinalPower:
    def test_positive_value(self, sample_actor, sample_target):
        effects = [{"timing": "PRE_MATCH", "type": "MODIFY_FINAL_POWER", "value": 5}]

        bonus, logs, changes = process_skill_effects(
            effects, "PRE_MATCH", sample_actor, sample_target
        )

        final_changes = [c for c in changes if c[1] == "MODIFY_FINAL_POWER"]
        assert len(final_changes) == 1
        assert final_changes[0][0] is sample_target
        assert final_changes[0][2] is None
        assert final_changes[0][3] == 5
        assert any("[最終威力 +5]" in log for log in logs)

    def test_negative_value(self, sample_actor, sample_target):
        effects = [{"timing": "PRE_MATCH", "type": "MODIFY_FINAL_POWER", "value": -3}]

        bonus, logs, changes = process_skill_effects(
            effects, "PRE_MATCH", sample_actor, sample_target
        )

        final_changes = [c for c in changes if c[1] == "MODIFY_FINAL_POWER"]
        assert len(final_changes) == 1
        assert final_changes[0][3] == -3
        assert any("[最終威力 -3]" in log for log in logs)

    def test_zero_value_is_ignored(self, sample_actor, sample_target):
        effects = [{"timing": "PRE_MATCH", "type": "MODIFY_FINAL_POWER", "value": 0}]

        bonus, logs, changes = process_skill_effects(
            effects, "PRE_MATCH", sample_actor, sample_target
        )

        assert [c for c in changes if c[1] == "MODIFY_FINAL_POWER"] == []


class TestDrainHp:
    def test_drain_heals_actor_based_on_base_damage(self, sample_actor, sample_target):
        # base_damage=20, rate=0.5, target hp=80 (>20) -> heal 10
        effects = [{"timing": "HIT", "type": "DRAIN_HP", "value": 0.5}]

        bonus, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target, base_damage=20
        )

        heal_changes = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "HP"]
        assert len(heal_changes) == 1
        assert heal_changes[0][0] is sample_actor
        assert heal_changes[0][3] == 10
        assert any("[吸収 +10]" in log for log in logs)

    def test_drain_is_capped_by_target_current_hp(self, sample_actor, sample_target):
        # 与ダメがオーバーキルの場合、対象の残HPを計算基準にする
        sample_target["hp"] = 6
        effects = [{"timing": "HIT", "type": "DRAIN_HP", "value": 0.5}]

        bonus, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target, base_damage=20
        )

        heal_changes = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "HP"]
        assert len(heal_changes) == 1
        assert heal_changes[0][3] == 3
        assert any("[吸収 +3]" in log for log in logs)

    def test_no_drain_when_base_damage_is_zero(self, sample_actor, sample_target):
        effects = [{"timing": "HIT", "type": "DRAIN_HP", "value": 0.5}]

        bonus, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target, base_damage=0
        )

        assert [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "HP"] == []
        assert not any("吸収" in log for log in logs)
