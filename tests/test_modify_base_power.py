# tests/test_modify_base_power.py
"""
MODIFY_BASE_POWER エフェクトタイプのユニットテスト
"""
import pytest
from manager.game_logic import process_skill_effects


class TestModifyBasePowerEffect:
    """MODIFY_BASE_POWER エフェクトのテスト"""

    def test_modify_base_power_applied_to_target(self, sample_actor, sample_target):
        """MODIFY_BASE_POWERがターゲットに適用される"""
        # Arrange: 守備スキルを持つターゲットに対して基礎威力+3を与えるエフェクト
        target_skill_data = {
            "tags": ["守備"],
            "分類": "防御",
            "基礎威力": 10
        }

        effects = [{
            "timing": "PRE_MATCH",
            "type": "MODIFY_BASE_POWER",
            "target": "target",
            "value": 3,
            "condition": {
                "source": "target_skill",
                "param": "tags",
                "operator": "CONTAINS",
                "value": "守備"
            }
        }]

        # Act: PRE_MATCHタイミングで効果を処理
        bonus_dmg, logs, changes = process_skill_effects(
            effects, "PRE_MATCH", sample_actor, sample_target, target_skill_data
        )

        # Assert: MODIFY_BASE_POWER の変更が適用される
        base_power_changes = [c for c in changes if c[1] == "MODIFY_BASE_POWER"]
        assert len(base_power_changes) == 1, "MODIFY_BASE_POWER が1つあるべき"
        assert base_power_changes[0][3] == 3, "値は+3であるべき"
        assert any("基礎威力 +3" in log for log in logs), "ログに基礎威力+3が含まれるべき"

    def test_modify_base_power_condition_not_met(self, sample_actor, sample_target):
        """条件が満たされない場合はMODIFY_BASE_POWERが適用されない"""
        # Arrange: 守備タグを持たないスキル
        target_skill_data = {
            "tags": ["攻撃"],
            "分類": "物理",
            "基礎威力": 15
        }

        effects = [{
            "timing": "PRE_MATCH",
            "type": "MODIFY_BASE_POWER",
            "target": "target",
            "value": 3,
            "condition": {
                "source": "target_skill",
                "param": "tags",
                "operator": "CONTAINS",
                "value": "守備"
            }
        }]

        # Act
        bonus_dmg, logs, changes = process_skill_effects(
            effects, "PRE_MATCH", sample_actor, sample_target, target_skill_data
        )

        # Assert: 条件不一致のため変更なし
        base_power_changes = [c for c in changes if c[1] == "MODIFY_BASE_POWER"]
        assert len(base_power_changes) == 0, "条件不一致なので変更なし"

    def test_modify_base_power_without_condition(self, sample_actor, sample_target):
        """条件なしのMODIFY_BASE_POWERは常に適用される"""
        effects = [{
            "timing": "PRE_MATCH",
            "type": "MODIFY_BASE_POWER",
            "target": "target",
            "value": 5
        }]

        # Act
        bonus_dmg, logs, changes = process_skill_effects(
            effects, "PRE_MATCH", sample_actor, sample_target, None
        )

        # Assert
        base_power_changes = [c for c in changes if c[1] == "MODIFY_BASE_POWER"]
        assert len(base_power_changes) == 1
        assert base_power_changes[0][3] == 5

    def test_modify_base_power_negative_value(self, sample_actor, sample_target):
        """マイナス値のMODIFY_BASE_POWERも動作する"""
        effects = [{
            "timing": "PRE_MATCH",
            "type": "MODIFY_BASE_POWER",
            "target": "target",
            "value": -2
        }]

        # Act
        bonus_dmg, logs, changes = process_skill_effects(
            effects, "PRE_MATCH", sample_actor, sample_target, None
        )

        # Assert
        base_power_changes = [c for c in changes if c[1] == "MODIFY_BASE_POWER"]
        assert len(base_power_changes) == 1
        assert base_power_changes[0][3] == -2
        assert any("基礎威力 -2" in log for log in logs), "ログに基礎威力-2が含まれるべき"
