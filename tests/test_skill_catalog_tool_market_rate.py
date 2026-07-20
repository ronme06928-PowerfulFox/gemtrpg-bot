from scripts.skill_catalog_tool import (
    build_market_rate_markdown,
    load_skills,
)


def test_market_rate_report_is_generated_from_current_cache():
    """相場レポートはF02を同期対象にせず、現在のキャッシュからオンデマンド生成する。"""
    skills = load_skills()
    body = build_market_rate_markdown(skills)
    assert f"全{len(skills)}件" in body
    assert "オンデマンド生成" in body
    assert "F02_Battle_Balance_Designer_Skill_Manual.md" in body


def test_state_apply_table_excludes_resource_stats():
    """出血/破裂等の状態異常表に FP/MP/HP のリソース増減が混入しないこと。"""
    skills = load_skills()
    body = build_market_rate_markdown(skills)
    section = body.split("### 状態異常の付与量相場", 1)[1].split("### 効果タイプ別の注意", 1)[0]
    for resource in ("| HP ", "| MP ", "| FP "):
        assert resource not in section, f"{resource.strip()} が状態異常表に混入している"
