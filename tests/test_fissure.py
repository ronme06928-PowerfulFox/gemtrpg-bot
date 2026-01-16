# tests/test_fissure.py
"""
亀裂システムのユニットテスト
"""
import pytest
from manager.game_logic import process_skill_effects
from manager.utils import get_status_value, set_status_value


class TestFissureApplication:
    """亀裂付与のテスト"""

    def test_fissure_first_application_succeeds(self, sample_actor, sample_target):
        """1ラウンド中の最初の亀裂付与は成功する"""
        # Arrange: 亀裂付与効果を持つスキルを用意
        effects = [{
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "亀裂",
            "value": 5
        }]

        # Act: 効果を処理
        bonus_dmg, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        # Assert: 亀裂の付与とフラグ設定が含まれている
        state_changes = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "亀裂"]
        flag_changes = [c for c in changes if c[1] == "SET_FLAG" and c[2] == "fissure_received_this_round"]

        assert len(state_changes) == 1, "亀裂の APPLY_STATE が1つあるべき"
        assert state_changes[0][3] == 5, "亀裂の付与値は5"
        assert len(flag_changes) == 1, "フラグ SET_FLAG が1つあるべき"
        assert flag_changes[0][3] is True, "フラグ値は True"

    def test_fissure_second_application_blocked(self, sample_actor, sample_target):
        """同一ラウンド中の2回目の亀裂付与はブロックされる"""
        # Arrange: ターゲットに既に今ラウンド亀裂が付与されているフラグを設定
        sample_target['flags'] = {'fissure_received_this_round': True}
        set_status_value(sample_target, '亀裂', 5)  # 既に5の亀裂がある

        effects = [{
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "亀裂",
            "value": 3
        }]

        # Act: 効果を処理
        bonus_dmg, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        # Assert: 亀裂の付与がない（スキップされた）
        state_changes = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "亀裂"]
        assert len(state_changes) == 0, "亀裂の APPLY_STATE は発生しないべき"

        # ログに失敗メッセージが含まれる
        assert any("付与失敗" in log for log in logs), "付与失敗のログがあるべき"

    def test_fissure_negative_value_not_blocked(self, sample_actor, sample_target):
        """亀裂の減少（負の値）は制限されない"""
        # Arrange: フラグが立っていても負の値は許容される
        sample_target['flags'] = {'fissure_received_this_round': True}
        set_status_value(sample_target, '亀裂', 10)

        effects = [{
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "亀裂",
            "value": -5  # 亀裂を減らす
        }]

        # Act
        bonus_dmg, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        # Assert: 負の値は制限されない
        state_changes = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "亀裂"]
        assert len(state_changes) == 1, "負の値の APPLY_STATE は許容されるべき"
        assert state_changes[0][3] == -5

    def test_other_states_not_affected(self, sample_actor, sample_target):
        """亀裂以外の状態付与は制限されない"""
        # Arrange: 出血の付与
        sample_target['flags'] = {'fissure_received_this_round': True}  # 亀裂フラグは関係ない

        effects = [{
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "出血",
            "value": 10
        }]

        # Act
        bonus_dmg, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        # Assert: 出血は正常に付与される
        state_changes = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "出血"]
        assert len(state_changes) == 1
        assert state_changes[0][3] == 10


class TestMultipleEffects:
    """複数効果のテスト"""

    def test_fissure_blocked_but_other_effects_applied(self, sample_actor, sample_target):
        """亀裂がブロックされても他の効果は適用される（案A）"""
        # Arrange
        sample_target['flags'] = {'fissure_received_this_round': True}

        effects = [
            {
                "timing": "HIT",
                "type": "APPLY_STATE",
                "target": "target",
                "state_name": "亀裂",
                "value": 5
            },
            {
                "timing": "HIT",
                "type": "APPLY_STATE",
                "target": "target",
                "state_name": "出血",
                "value": 3
            },
            {
                "timing": "HIT",
                "type": "DAMAGE_BONUS",
                "value": 10
            }
        ]

        # Act
        bonus_dmg, logs, changes = process_skill_effects(
            effects, "HIT", sample_actor, sample_target
        )

        # Assert
        fissure_changes = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "亀裂"]
        bleed_changes = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "出血"]

        assert len(fissure_changes) == 0, "亀裂はブロックされる"
        assert len(bleed_changes) == 1, "出血は適用される"
        assert bonus_dmg == 10, "ダメージボーナスも適用される"
