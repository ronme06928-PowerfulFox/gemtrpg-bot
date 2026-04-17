import manager.game_logic as game_logic


def test_preview_range_without_physical_placeholder(monkeypatch):
    monkeypatch.setattr(game_logic, "get_buff_stat_mod", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(game_logic, "get_status_value", lambda *_args, **_kwargs: 0)

    actor = {
        "id": "actor-1",
        "name": "テスト使用者",
        "initial_data": {
            "物理補正": 0,
            "魔法補正": 0,
            "ダイス威力": 0,
        },
    }
    target = {"id": "target-1", "name": "テスト対象"}
    skill_data = {
        "基礎威力": 4,
        "チャットパレット": "4+1d5 【E-26 遅いんじゃないか？】",
    }

    preview = game_logic.calculate_skill_preview(actor, target, skill_data)

    assert preview["final_command"] == "4+1d5"
    assert int(preview["min_damage"]) == 5
    assert int(preview["max_damage"]) == 9
