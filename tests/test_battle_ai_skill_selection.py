from manager.battle import battle_ai


def test_extract_skill_ids_from_commands_supports_fullwidth_and_brackets():
    commands = "\n".join([
        "9+1d6 【S-01：斬撃】",
        "8+1d6 【S_02 Slash】",
        "7+1d6 [S-03 Test]",
        "6+1d6 【S-01 重複】",
    ])
    ids = battle_ai._extract_skill_ids_from_commands(commands)
    assert ids == ["S-01", "S_02", "S-03"]


def test_list_usable_skill_ids_filters_by_cost_and_instant(monkeypatch):
    skill_map = {
        "S-ATK": {"name": "Attack", "tags": []},
        "S-INST": {"name": "Instant", "tags": ["即時発動"]},
        "S-COST": {"name": "Costly", "tags": []},
    }
    char = {
        "name": "Enemy",
        "commands": "【S-ATK】\n【S-INST】\n【S-COST】",
    }

    monkeypatch.setattr(battle_ai, "all_skill_data", skill_map)

    def _fake_verify(_char, skill_data):
        if skill_data.get("name") == "Costly":
            return False, "no resource"
        return True, ""

    monkeypatch.setattr(battle_ai, "verify_skill_cost", _fake_verify)
    usable = battle_ai.list_usable_skill_ids(char, allow_instant=False)
    assert usable == ["S-ATK"]


def test_ai_suggest_skill_chooses_from_usable_pool(monkeypatch):
    skill_map = {
        "S-A": {"name": "A", "tags": []},
        "S-B": {"name": "B", "tags": []},
    }
    char = {
        "name": "Enemy",
        "commands": "【S-A】\n【S-B】",
    }

    monkeypatch.setattr(battle_ai, "all_skill_data", skill_map)
    monkeypatch.setattr(battle_ai, "verify_skill_cost", lambda _c, _s: (True, ""))
    monkeypatch.setattr(battle_ai.random, "choice", lambda seq: seq[0])

    suggested = battle_ai.ai_suggest_skill(char)
    assert suggested == "S-A"


def test_ai_suggest_skill_returns_none_when_pool_empty(monkeypatch):
    char = {
        "name": "Enemy",
        "commands": "【S-NOPE】",
    }

    monkeypatch.setattr(battle_ai, "all_skill_data", {})
    monkeypatch.setattr(battle_ai, "verify_skill_cost", lambda _c, _s: (True, ""))

    suggested = battle_ai.ai_suggest_skill(char)
    assert suggested is None
