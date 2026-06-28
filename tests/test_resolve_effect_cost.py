"""
_apply_cost のユニットテスト（Plan 10 §10.5）

検証ポイント:
  - 基本コスト（制約なし）の消費
  - actor 由来の add_cost 制約込みの消費
  - skill dict に effective_cost が埋め込まれている場合の消費（field-effect 経由）
  - コスト 0 のスキルは何も消費しない
  - policy が COST_CONSUME_POLICY でなければ消費しない
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manager.battle.resolve_effect_runtime import _apply_cost, COST_CONSUME_POLICY


# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------

def _actor(fp=5, mp=10, hp=30):
    return {
        "id": "A1",
        "hp": hp,
        "mp": mp,
        "states": [{"name": "FP", "value": fp}],
        "special_buffs": [],
        "flags": {},
        "commands": "",
    }


def _skill(skill_id="P-01", fp_cost=0, mp_cost=0, effective_cost=None):
    """skill dict を作成。effective_cost を直接埋め込む場合は引数で渡す。"""
    cost_entries = []
    if fp_cost > 0:
        cost_entries.append({"type": "FP", "value": fp_cost})
    if mp_cost > 0:
        cost_entries.append({"type": "MP", "value": mp_cost})
    d = {
        "id": skill_id,
        "rule_data": {"schema": "skill_json_rule_v2", "cost": cost_entries},
    }
    if effective_cost is not None:
        d["effective_cost"] = effective_cost
    return d


# ---------------------------------------------------------------------------
# 基本コスト消費
# ---------------------------------------------------------------------------

def test_apply_cost_consumes_fp(monkeypatch):
    actor = _actor(fp=5)
    skill = _skill("P-01", fp_cost=2)
    monkeypatch.setattr(
        "manager.battle.resolve_effect_runtime.all_skill_data",
        {"P-01": skill},
    )
    result = _apply_cost(actor, skill, COST_CONSUME_POLICY)
    assert result["fp"] == 2
    fp_state = next(s for s in actor["states"] if s["name"] == "FP")
    assert fp_state["value"] == 3  # 5 - 2


def test_apply_cost_consumes_mp(monkeypatch):
    actor = _actor(mp=10)
    skill = _skill("M-01", mp_cost=3)
    monkeypatch.setattr(
        "manager.battle.resolve_effect_runtime.all_skill_data",
        {"M-01": skill},
    )
    result = _apply_cost(actor, skill, COST_CONSUME_POLICY)
    assert result["mp"] == 3
    assert actor["mp"] == 7  # 10 - 3


def test_apply_cost_zero_cost_skill_consumes_nothing(monkeypatch):
    actor = _actor(fp=5, mp=10)
    skill = _skill("Z-01")  # コストなし
    monkeypatch.setattr(
        "manager.battle.resolve_effect_runtime.all_skill_data",
        {"Z-01": skill},
    )
    result = _apply_cost(actor, skill, COST_CONSUME_POLICY)
    assert result["fp"] == 0
    assert result["mp"] == 0


def test_apply_cost_wrong_policy_consumes_nothing(monkeypatch):
    actor = _actor(fp=5)
    skill = _skill("P-01", fp_cost=2)
    monkeypatch.setattr(
        "manager.battle.resolve_effect_runtime.all_skill_data",
        {"P-01": skill},
    )
    result = _apply_cost(actor, skill, "wrong_policy")
    assert result["fp"] == 0
    fp_state = next(s for s in actor["states"] if s["name"] == "FP")
    assert fp_state["value"] == 5  # 変化なし


# ---------------------------------------------------------------------------
# actor 由来 add_cost 込みの消費
# ---------------------------------------------------------------------------

def test_apply_cost_respects_actor_add_cost_constraint(monkeypatch):
    """special_buffs の add_cost 制約がコスト消費に反映される"""
    actor = _actor(fp=5)
    actor["special_buffs"] = [
        {
            "name": "Pressure",
            "data": {
                "skill_constraints": [
                    {
                        "id": "ac-r1",
                        "mode": "add_cost",
                        "match": {"cost_types": ["FP"]},
                        "add_cost": [{"type": "FP", "value": 2}],
                    }
                ]
            },
        }
    ]
    skill = _skill("P-01", fp_cost=1)
    monkeypatch.setattr(
        "manager.battle.resolve_effect_runtime.all_skill_data",
        {"P-01": skill},
    )
    result = _apply_cost(actor, skill, COST_CONSUME_POLICY)
    # 基本 FP=1, add_cost FP=2 → 合計 3 消費
    assert result["fp"] == 3
    fp_state = next(s for s in actor["states"] if s["name"] == "FP")
    assert fp_state["value"] == 2  # 5 - 3


# ---------------------------------------------------------------------------
# effective_cost 直埋め込み（field-effect 由来の add_cost 正確消費）
# ---------------------------------------------------------------------------

def test_apply_cost_uses_embedded_effective_cost(monkeypatch):
    """skill dict に effective_cost が埋め込まれていれば、それを優先して消費する。
    これは field_effects 由来の add_cost が正しく消費されることを保証するパス
    （resolve_auto_single_phase が intent.effective_cost を埋め込む）。
    """
    actor = _actor(fp=5)
    # effective_cost には FP=3（基本1 + field add_cost 2）を直接指定
    skill = _skill("P-01", fp_cost=1, effective_cost=[{"type": "FP", "value": 3}])
    monkeypatch.setattr(
        "manager.battle.resolve_effect_runtime.all_skill_data",
        {"P-01": skill},
    )
    result = _apply_cost(actor, skill, COST_CONSUME_POLICY)
    assert result["fp"] == 3
    fp_state = next(s for s in actor["states"] if s["name"] == "FP")
    assert fp_state["value"] == 2  # 5 - 3


def test_apply_cost_embedded_effective_cost_takes_priority_over_actor_constraints(monkeypatch):
    """effective_cost が埋め込まれていれば actor 制約の再計算を行わない。
    commit 時の評価値が正とみなされる。
    """
    actor = _actor(fp=5)
    # actor 側にも add_cost があるが、embedded effective_cost が FP=2 → FP=2 消費
    actor["special_buffs"] = [
        {
            "name": "Pressure",
            "data": {
                "skill_constraints": [
                    {
                        "id": "ac-r2",
                        "mode": "add_cost",
                        "match": {"cost_types": ["FP"]},
                        "add_cost": [{"type": "FP", "value": 10}],  # 大きな add_cost
                    }
                ]
            },
        }
    ]
    skill = _skill("P-01", fp_cost=1, effective_cost=[{"type": "FP", "value": 2}])
    monkeypatch.setattr(
        "manager.battle.resolve_effect_runtime.all_skill_data",
        {"P-01": skill},
    )
    result = _apply_cost(actor, skill, COST_CONSUME_POLICY)
    # embedded の FP=2 が使われる（actor の add_cost=10 は再評価されない）
    assert result["fp"] == 2
    fp_state = next(s for s in actor["states"] if s["name"] == "FP")
    assert fp_state["value"] == 3  # 5 - 2


# ---------------------------------------------------------------------------
# FP が足りない場合でも 0 下限でクランプ
# ---------------------------------------------------------------------------

def test_apply_cost_fp_clamps_to_zero(monkeypatch):
    actor = _actor(fp=1)
    skill = _skill("P-01", fp_cost=5)  # FP より多く要求
    monkeypatch.setattr(
        "manager.battle.resolve_effect_runtime.all_skill_data",
        {"P-01": skill},
    )
    result = _apply_cost(actor, skill, COST_CONSUME_POLICY)
    # 消費は実際にある分だけ
    assert result["fp"] == 1
    fp_state = next(s for s in actor["states"] if s["name"] == "FP")
    assert fp_state["value"] == 0
