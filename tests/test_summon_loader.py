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
    assert param_map["速度"] == 8
    assert param_map["物理補正"] == 1
    assert param_map["魔法補正"] == 0

    t1 = templates["U-01"]
    assert t1["summon_duration_mode"] == "permanent"
    assert t1["summon_duration"] == 0
    assert t1["allow_duplicate_same_team"] is True
