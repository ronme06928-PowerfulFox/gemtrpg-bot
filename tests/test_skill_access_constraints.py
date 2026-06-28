import pytest

from manager.battle import skill_access
from manager.battle.system_skills import SYS_STRUGGLE_ID


def _char(fp=3, mp=0, commands="", actor_type=""):
    c = {
        "id": "A1",
        "name": "Actor",
        "commands": commands,
        "states": [{"name": "FP", "value": int(fp)}],
        "special_buffs": [],
        "flags": {},
    }
    if mp:
        c["mp"] = int(mp)  # MP は states ではなく直接フィールドで保持（_fallback_get_status_value の仕様）
    if actor_type:
        c["type"] = actor_type
    return c


_SKILL_FP1 = {
    "id": "P-01",
    "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]},
}
_SKILL_MP1 = {
    "id": "M-01",
    "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "MP", "value": 1}]},
}


def test_evaluate_skill_access_blocks_by_flag_constraint(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "r1", "mode": "block", "match": {"cost_types": ["FP"]}, "reason": "FP cost blocked"}
    ]
    monkeypatch.setattr(
        skill_access,
        "all_skill_data",
        {"P-01": {"id": "P-01", "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]}}},
    )

    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert "FP cost blocked" in ev["blocked_reasons"]


def test_evaluate_skill_access_add_cost_causes_insufficient(monkeypatch):
    actor = _char(fp=1, commands="[P-01 Test]")
    actor["special_buffs"] = [
        {
            "name": "Pressure",
            "data": {
                "skill_constraints": [
                    {"id": "r2", "mode": "add_cost", "match": {"cost_types": ["FP"]}, "add_cost": [{"type": "FP", "value": 1}]}
                ]
            },
        }
    ]
    monkeypatch.setattr(
        skill_access,
        "all_skill_data",
        {"P-01": {"id": "P-01", "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]}}},
    )

    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert any("FP" in r for r in ev["blocked_reasons"])
    assert ev["effective_cost"] == [{"type": "FP", "value": 2}]


def test_list_usable_skill_ids_falls_back_to_sys_struggle(monkeypatch):
    actor = _char(fp=0, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [{"mode": "block", "match": {"skill_id": "p-01"}, "reason": "blocked"}]
    monkeypatch.setattr(
        skill_access,
        "all_skill_data",
        {
            "P-01": {"id": "P-01", "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]}},
            SYS_STRUGGLE_ID: {"id": SYS_STRUGGLE_ID, "rule_data": {"schema": "skill_json_rule_v2", "cost": []}},
        },
    )

    usable = skill_access.list_usable_skill_ids(actor, allow_fallback=True)
    assert usable == [SYS_STRUGGLE_ID]


# ---------------------------------------------------------------------------
# field_effects 経由の block
# ---------------------------------------------------------------------------

def test_block_via_battle_state_field_effects(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]")
    battle_state = {
        "field_effects": [
            {
                "skill_constraints": [
                    {"id": "fe-r1", "mode": "block", "match": {"cost_types": ["FP"]}, "reason": "フィールド封印"},
                ]
            }
        ]
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01", battle_state=battle_state)
    assert ev["usable"] is False
    assert "フィールド封印" in ev["blocked_reasons"]


def test_block_via_room_state_field_effects(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]")
    room_state = {
        "field_effects": [
            {
                "skill_constraints": [
                    {"id": "rs-r1", "mode": "block", "match": {"cost_types": ["FP"]}, "reason": "ルーム封印"},
                ]
            }
        ]
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01", room_state=room_state)
    assert ev["usable"] is False
    assert "ルーム封印" in ev["blocked_reasons"]


# ---------------------------------------------------------------------------
# stage_field_effect_profile.rules 経由の block（インライン制約形式）
# ---------------------------------------------------------------------------

def test_block_via_stage_field_effect_profile_rules(monkeypatch):
    # field_effects が空の場合に stage_field_effect_profile.rules が使われる
    actor = _char(fp=5, commands="[P-01 Test]")
    battle_state = {
        "field_effects": [],
        "stage_field_effect_profile": {
            "rules": [
                {"mode": "block", "match": {"cost_types": ["FP"]}, "reason": "ステージ封印"},
            ]
        },
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01", battle_state=battle_state)
    assert ev["usable"] is False
    assert "ステージ封印" in ev["blocked_reasons"]


def test_block_not_applied_when_field_effects_present(monkeypatch):
    # field_effects が存在する場合は stage_field_effect_profile.rules を無視する
    actor = _char(fp=5, commands="[P-01 Test]")
    battle_state = {
        "field_effects": [{"skill_constraints": []}],  # 空でも非 empty list なら優先
        "stage_field_effect_profile": {
            "rules": [
                {"mode": "block", "match": {"cost_types": ["FP"]}, "reason": "無視されるはず"},
            ]
        },
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01", battle_state=battle_state)
    assert ev["usable"] is True


# ---------------------------------------------------------------------------
# category マッチ（物理 / 魔法 / 補助）
# ---------------------------------------------------------------------------

def test_block_by_category_match(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "cat-r1", "mode": "block", "match": {"category": "物理"}, "reason": "物理スキル封印"},
    ]
    skill = {"id": "P-01", "category": "物理", "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]}}
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": skill})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert "物理スキル封印" in ev["blocked_reasons"]


def test_block_by_category_does_not_hit_other_category(monkeypatch):
    # 魔法封印が物理スキルに命中しない
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "cat-r2", "mode": "block", "match": {"category": "魔法"}, "reason": "魔法スキル封印"},
    ]
    skill = {"id": "P-01", "category": "物理", "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]}}
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": skill})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is True


def test_block_category_falls_back_to_rule_data(monkeypatch):
    # スキル本体に category がなく rule_data.category を参照するケース
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "cat-r3", "mode": "block", "match": {"category": "補助"}, "reason": "補助封印"},
    ]
    skill = {
        "id": "P-01",
        "rule_data": {"schema": "skill_json_rule_v2", "category": "補助", "cost": [{"type": "FP", "value": 1}]},
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": skill})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert "補助封印" in ev["blocked_reasons"]


# ---------------------------------------------------------------------------
# scope フィルタ（ally / enemy / except_source）
# ---------------------------------------------------------------------------

def test_scope_enemy_skips_ally_actor(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]", actor_type="ally")
    battle_state = {
        "field_effects": [
            {
                "scope": "enemy",
                "skill_constraints": [{"id": "sc-r1", "mode": "block", "match": {}, "reason": "敵専用封印"}],
            }
        ]
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01", battle_state=battle_state)
    assert ev["usable"] is True


def test_scope_enemy_applies_to_enemy_actor(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]", actor_type="enemy")
    battle_state = {
        "field_effects": [
            {
                "scope": "enemy",
                "skill_constraints": [{"id": "sc-r2", "mode": "block", "match": {}, "reason": "敵専用封印"}],
            }
        ]
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01", battle_state=battle_state)
    assert ev["usable"] is False
    assert "敵専用封印" in ev["blocked_reasons"]


def test_scope_except_source_skips_matching_slot(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]")
    battle_state = {
        "field_effects": [
            {
                "scope": "except_source",
                "source_slot_id": "slot-A",
                "skill_constraints": [{"id": "sc-r3", "mode": "block", "match": {}, "reason": "発生源除外封印"}],
            }
        ]
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    # slot_id が source_slot_id と一致する場合はスキップ
    ev = skill_access.evaluate_skill_access(actor, "P-01", battle_state=battle_state, slot_id="slot-A")
    assert ev["usable"] is True


def test_scope_except_source_applies_to_other_slot(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]")
    battle_state = {
        "field_effects": [
            {
                "scope": "except_source",
                "source_slot_id": "slot-A",
                "skill_constraints": [{"id": "sc-r4", "mode": "block", "match": {}, "reason": "発生源除外封印"}],
            }
        ]
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    # slot_id が異なる場合は適用される
    ev = skill_access.evaluate_skill_access(actor, "P-01", battle_state=battle_state, slot_id="slot-B")
    assert ev["usable"] is False
    assert "発生源除外封印" in ev["blocked_reasons"]


# ---------------------------------------------------------------------------
# 複数 block 同時命中
# ---------------------------------------------------------------------------

def test_multiple_blocks_return_all_reasons(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "b1", "mode": "block", "match": {"cost_types": ["FP"]}, "reason": "理由A"},
        {"id": "b2", "mode": "block", "match": {"skill_id": "p-01"}, "reason": "理由B"},
    ]
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert "理由A" in ev["blocked_reasons"]
    assert "理由B" in ev["blocked_reasons"]
    assert len(ev["blocked_reasons"]) == 2


# ---------------------------------------------------------------------------
# add_cost + block 同時：block が先に判定され理由として返り、コスト不足チェックは走らない
# ---------------------------------------------------------------------------

def test_block_reason_returned_not_cost_insufficiency(monkeypatch):
    # FP=2, 基本コスト=1, add_cost=+10 → cost不足だが block が先に返る
    actor = _char(fp=2, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "b1", "mode": "block", "match": {"cost_types": ["FP"]}, "reason": "封印"},
        {"id": "c1", "mode": "add_cost", "match": {"cost_types": ["FP"]}, "add_cost": [{"type": "FP", "value": 10}]},
    ]
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    # blocked_reasons は block の理由のみ（コスト不足メッセージではない）
    assert ev["blocked_reasons"] == ["封印"]
    # effective_cost には add_cost が乗った値が返る（計算自体はされる）
    assert ev["effective_cost"] == [{"type": "FP", "value": 11}]


# ---------------------------------------------------------------------------
# duplicate constraint id 検知（クロスソース）
# ---------------------------------------------------------------------------

def test_duplicate_constraint_id_cross_source_causes_error(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "dup-id", "mode": "block", "match": {}, "reason": "from flags"},
    ]
    actor["special_buffs"] = [
        {
            "name": "Buff",
            "data": {
                "skill_constraints": [
                    {"id": "dup-id", "mode": "block", "match": {}, "reason": "from buff"},
                ]
            },
        }
    ]
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert any("dup-id" in r for r in ev["blocked_reasons"])


# ---------------------------------------------------------------------------
# MP add_cost / 複数コスト種別加算
# ---------------------------------------------------------------------------

def test_add_cost_mp_causes_insufficient(monkeypatch):
    actor = _char(fp=5, mp=1, commands="[M-01 Test]")
    actor["special_buffs"] = [
        {
            "name": "MPDrain",
            "data": {
                "skill_constraints": [
                    {"id": "mp-r1", "mode": "add_cost", "match": {"cost_types": ["MP"]}, "add_cost": [{"type": "MP", "value": 2}]},
                ]
            },
        }
    ]
    monkeypatch.setattr(skill_access, "all_skill_data", {"M-01": _SKILL_MP1})
    ev = skill_access.evaluate_skill_access(actor, "M-01")
    assert ev["usable"] is False
    assert any("MP" in r for r in ev["blocked_reasons"])
    assert ev["effective_cost"] == [{"type": "MP", "value": 3}]


def test_add_cost_multiple_types_merged(monkeypatch):
    # FP と MP の両方にコスト増加が乗り、両方払える場合は usable
    actor = _char(fp=5, mp=10, commands="[X-01 Test]")
    actor["special_buffs"] = [
        {
            "name": "Drain",
            "data": {
                "skill_constraints": [
                    {
                        "id": "mc-r1",
                        "mode": "add_cost",
                        "match": {},
                        "add_cost": [{"type": "FP", "value": 1}, {"type": "MP", "value": 2}],
                    }
                ]
            },
        }
    ]
    skill = {
        "id": "X-01",
        "rule_data": {
            "schema": "skill_json_rule_v2",
            "cost": [{"type": "FP", "value": 1}, {"type": "MP", "value": 1}],
        },
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"X-01": skill})
    ev = skill_access.evaluate_skill_access(actor, "X-01")
    assert ev["usable"] is True  # FP=5>=2, MP=10>=3
    cost_map = {e["type"]: e["value"] for e in ev["effective_cost"]}
    assert cost_map["FP"] == 2
    assert cost_map["MP"] == 3


def test_add_cost_multiple_rules_same_type_accumulate(monkeypatch):
    # 複数の add_cost ルールが同一コスト種別に加算される（単純和）
    actor = _char(fp=2, commands="[P-01 Test]")
    actor["special_buffs"] = [
        {"name": "Buff1", "data": {"skill_constraints": [
            {"id": "ac-r1", "mode": "add_cost", "match": {"cost_types": ["FP"]}, "add_cost": [{"type": "FP", "value": 1}]},
        ]}},
        {"name": "Buff2", "data": {"skill_constraints": [
            {"id": "ac-r2", "mode": "add_cost", "match": {"cost_types": ["FP"]}, "add_cost": [{"type": "FP", "value": 1}]},
        ]}},
    ]
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": _SKILL_FP1})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    # 基本 FP=1, +1, +1 → 合計 3, FP=2 なので不足
    assert ev["usable"] is False
    assert ev["effective_cost"] == [{"type": "FP", "value": 3}]


# ---------------------------------------------------------------------------
# 実キャッシュ形式（日本語キー）でのカテゴリ・距離マッチ
# skills_cache.json は "分類" / "距離" / "属性" の日本語キーを使う。
# build_skill_reference がこれらを正しく拾えることを確認する。
# ---------------------------------------------------------------------------

def test_block_by_category_using_japanese_key(monkeypatch):
    # 実スキルキャッシュ形式: "分類" キーを使う
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "jk-r1", "mode": "block", "match": {"category": "物理"}, "reason": "物理封印"},
    ]
    skill = {
        "スキルID": "P-01",
        "分類": "物理",
        "特記処理": "{\"schema\":\"skill_json_rule_v2\",\"cost\":[{\"type\":\"FP\",\"value\":1}]}",
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": skill})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert "物理封印" in ev["blocked_reasons"]


def test_block_by_distance_using_japanese_key(monkeypatch):
    # 実スキルキャッシュ形式: "距離" キーを使う
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "jk-r2", "mode": "block", "match": {"distance": "近接"}, "reason": "近接封印"},
    ]
    skill = {
        "スキルID": "P-01",
        "距離": "近接",
        "特記処理": "{\"schema\":\"skill_json_rule_v2\",\"cost\":[{\"type\":\"FP\",\"value\":1}]}",
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": skill})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert "近接封印" in ev["blocked_reasons"]


def test_japanese_key_category_does_not_hit_other_category(monkeypatch):
    # "分類": "魔法" のスキルは "category": "物理" の block に命中しない
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "jk-r3", "mode": "block", "match": {"category": "物理"}, "reason": "物理封印"},
    ]
    skill = {
        "スキルID": "P-01",
        "分類": "魔法",
        "特記処理": "{\"schema\":\"skill_json_rule_v2\",\"cost\":[{\"type\":\"FP\",\"value\":1}]}",
    }
    monkeypatch.setattr(skill_access, "all_skill_data", {"P-01": skill})
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is True
