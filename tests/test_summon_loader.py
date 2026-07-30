from manager.summons import loader as summon_loader


class _DummyResponse:
    def __init__(self, text):
        self.status_code = 200
        self.text = text
        self.encoding = "utf-8"

    def raise_for_status(self):
        return None


def test_fetch_summon_templates_from_csv_parses_duration_and_params(monkeypatch):
    csv_text = (
        "ユニットID,表示名,HP,最大HP,MP,最大MP,戦闘スキル,持続設定,重複,パッシブスキル,輝化スキル,秘匿スキル,所持アイテム,速度,物理補正,魔法補正,特記JSON\n"
        "U-00,鉄の小蜘蛛,30,30,0,0,\"E-17,E-18\",3,不可,PA-01,RA-01,HS-01,\"I-01:2,I-02\",8,1,0,\n"
        "U-01,マフィアの下っ端,55,55,8,8,\"Ps-00,Ps-01,Ps-02\",-1,可,,,,,6,0,0,\n"
    )

    monkeypatch.setattr(
        summon_loader.requests,
        "get",
        lambda *_args, **_kwargs: _DummyResponse(csv_text),
    )

    templates = summon_loader.fetch_summon_templates_from_csv()

    t0 = templates["U-00"]
    assert t0["name"] == "鉄の小蜘蛛"
    assert t0["initial_skill_ids"] == ["E-17", "E-18"]
    assert t0["summon_duration_mode"] == "duration_rounds"
    assert t0["summon_duration"] == 3
    assert t0["allow_duplicate_same_team"] is False
    assert t0["SPassive"] == ["PA-01"]
    assert t0["radiance_skills"] == ["RA-01"]
    assert t0["hidden_skills"] == ["HS-01"]
    assert t0["inventory"] == {"I-01": 2, "I-02": 1}
    param_map = {p["label"]: int(p["value"]) for p in t0["params"]}
    assert param_map["敏捷"] == 8
    assert param_map["物理補正"] == 1
    assert param_map["魔法補正"] == 0

    t1 = templates["U-01"]
    assert t1["summon_duration_mode"] == "permanent"
    assert t1["summon_duration"] == 0
    assert t1["allow_duplicate_same_team"] is True


def test_extra_json_lists_are_normalized_and_passives_are_merged(monkeypatch):
    csv_text = (
        "ユニットID,表示名,HP,最大HP,パッシブスキル,特記JSON\n"
        'U-02,鉄交じりの瓦礫,30,30,"Pa-08,Pa-07",'
        '"{""tag_ids"":[""瓦礫"",""瓦礫""],'
        '""disabled_tag_ids"":[""機械""],'
        '""SPassive"":[""Pa-07""],'
        '""special_buffs"":[{""name"":""無言""}],'
        '""flags"":{""action_slot_mode"":""none""}}"\n'
    )
    monkeypatch.setattr(
        summon_loader.requests,
        "get",
        lambda *_args, **_kwargs: _DummyResponse(csv_text),
    )

    template = summon_loader.fetch_summon_templates_from_csv()["U-02"]

    assert template["tag_ids"] == ["瓦礫"]
    assert template["disabled_tag_ids"] == ["機械"]
    assert template["SPassive"] == ["Pa-07", "Pa-08"]
    assert template["special_buffs"] == [{"name": "無言"}]
    assert template["flags"] == {"action_slot_mode": "none"}


def test_empty_passive_column_preserves_extra_json_passives(monkeypatch):
    csv_text = (
        "ユニットID,表示名,HP,最大HP,パッシブスキル,特記JSON\n"
        'U-02,鉄交じりの瓦礫,30,30,,'
        '"{""SPassive"":[""Pa-07""]}"\n'
    )
    monkeypatch.setattr(
        summon_loader.requests,
        "get",
        lambda *_args, **_kwargs: _DummyResponse(csv_text),
    )

    template = summon_loader.fetch_summon_templates_from_csv()["U-02"]

    assert template["SPassive"] == ["Pa-07"]


def test_invalid_extra_json_contract_fields_fall_back_to_safe_values(caplog):
    row = {
        "template_id": "U-BAD",
        "extra_json": (
            '{"tag_ids":{"bad":true},"disabled_tag_ids":7,'
            '"SPassive":{"id":"Pa-07"},"special_buffs":"bad","flags":[]}'
        ),
    }

    template_id, template = summon_loader._build_row_template(row)

    assert template_id == "U-BAD"
    assert template["tag_ids"] == []
    assert template["disabled_tag_ids"] == []
    assert template["SPassive"] == []
    assert template["special_buffs"] == []
    assert template["flags"] == {}
    assert "U-BAD" in caplog.text
