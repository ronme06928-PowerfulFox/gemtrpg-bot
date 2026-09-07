import pytest

import manager.game_logic as game_logic


@pytest.fixture
def preview_dependencies(monkeypatch):
    def get_status_value(character, status_name):
        return character.get("status", {}).get(status_name, 0)

    def resolve_placeholders(text, character):
        for status_name in ("物理補正", "魔法補正"):
            text = text.replace(
                f"{{{status_name}}}", str(get_status_value(character, status_name))
            )
        return text

    monkeypatch.setattr(game_logic, "get_status_value", get_status_value)
    monkeypatch.setattr(game_logic, "get_buff_stat_mod", lambda *_args: 0)
    monkeypatch.setattr(game_logic, "get_buff_stat_mod_details", lambda *_args: [])
    monkeypatch.setattr(game_logic, "resolve_placeholders", resolve_placeholders)


@pytest.fixture
def actor():
    return {
        "id": "Actor1",
        "name": "Hero",
        "status": {"物理補正": 2, "魔法補正": 0, "戦慄": 0},
        "special_buffs": [],
    }


@pytest.fixture
def skill_data():
    return {
        "基礎威力": "5",
        "ダイス威力": "2d6",
        "チャットパレット": "【TestSkill】 5+2d6+{物理補正}",
    }


def test_basic_calc(preview_dependencies, actor, skill_data):
    preview = game_logic.calculate_skill_preview(actor, {"id": "Target1"}, skill_data)
    assert preview["min_damage"] == 9
    assert preview["max_damage"] == 19
    assert preview["final_command"] == "5+2d6+2"


def test_external_mod(preview_dependencies, actor, skill_data):
    preview = game_logic.calculate_skill_preview(
        actor, {"id": "Target1"}, skill_data, external_base_power_mod=-2
    )
    assert preview["min_damage"] == 7
    assert preview["max_damage"] == 17
    assert preview["final_command"].startswith("3+")


def test_senritsu(preview_dependencies, actor, skill_data):
    actor["status"]["戦慄"] = 2
    preview = game_logic.calculate_skill_preview(
        actor, {"id": "Target1"}, skill_data, senritsu_max_apply=3
    )
    assert preview["senritsu_dice_reduction"] == 2
    assert preview["max_damage"] == 15
    assert "2d4" in preview["final_command"]


def test_correction_delta_calculation(preview_dependencies, monkeypatch):
    actor = {
        "name": "TestActor",
        "params": [
            {"label": "基礎威力", "value": "10"},
            {"label": "物理補正", "value": "5"},
            {"label": "魔法補正", "value": "3"},
        ],
        "initial_data": {"物理補正": 5, "魔法補正": 3, "ダイス威力": 0},
        "special_buffs": [],
    }

    def current_status(_character, stat):
        return {"物理補正": 7, "魔法補正": 3}.get(stat, 0)

    monkeypatch.setattr(game_logic, "get_status_value", current_status)
    monkeypatch.setattr(game_logic, "get_buff_stat_mod", lambda *_args: 2)
    result = game_logic.calculate_skill_preview(
        actor,
        {},
        {
            "基礎威力": 0,
            "ダイス威力": "2d6+{物理補正}",
            "チャットパレット": "TestSkill:2d6+{物理補正}",
        },
    )

    corrections = result.get("correction_details", [])
    physical = next((item for item in corrections if item["source"] == "物理補正"), None)
    magical = next((item for item in corrections if item["source"] == "魔法補正"), None)
    assert physical is not None
    assert physical["value"] == 2
    assert magical is None
