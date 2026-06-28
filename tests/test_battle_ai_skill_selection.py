from manager.battle import battle_ai


def test_ai_suggest_skill_chooses_from_usable_pool(monkeypatch):
    char = {"name": "Enemy", "commands": "【S-A】\n【S-B】"}
    monkeypatch.setattr(battle_ai, "list_usable_skill_ids", lambda c, **kw: ["S-A", "S-B"])
    monkeypatch.setattr(battle_ai.random, "choice", lambda seq: seq[0])

    suggested = battle_ai.ai_suggest_skill(char)
    assert suggested == "S-A"


def test_ai_suggest_skill_returns_sys_struggle_when_all_skills_blocked(monkeypatch):
    char = {"name": "Enemy", "commands": "【S-A】"}
    monkeypatch.setattr(battle_ai, "list_usable_skill_ids", lambda c, **kw: ["SYS-STRUGGLE"])
    monkeypatch.setattr(battle_ai.random, "choice", lambda seq: seq[0])

    suggested = battle_ai.ai_suggest_skill(char)
    assert suggested == "SYS-STRUGGLE"


def test_ai_suggest_skill_returns_none_for_empty_char():
    assert battle_ai.ai_suggest_skill(None) is None
    assert battle_ai.ai_suggest_skill({}) is None
