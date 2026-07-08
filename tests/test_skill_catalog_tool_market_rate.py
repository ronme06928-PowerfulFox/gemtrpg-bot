from scripts.skill_catalog_tool import (
    F02_PATH,
    MARKET_RATE_BEGIN,
    MARKET_RATE_END,
    build_market_rate_markdown,
    load_skills,
)


def test_f02_market_rate_section_is_up_to_date():
    """計画書31 Phase2: F02 のB群相場表はキャッシュ実データと常に一致していること。

    `python scripts/skill_catalog_tool.py build-market-rate` の実行漏れをCIで検出する。
    """
    skills = load_skills()
    current_text = F02_PATH.read_text(encoding="utf-8")

    begin_idx = current_text.find(MARKET_RATE_BEGIN)
    end_idx = current_text.find(MARKET_RATE_END)
    assert begin_idx != -1 and end_idx != -1, "F02 に market-rate マーカーが見つからない"

    current_body = current_text[begin_idx + len(MARKET_RATE_BEGIN):end_idx].strip()

    # as_of はキャッシュファイルの mtime 由来で本文中に埋め込まれているため、
    # 生成し直した本文からそのまま抽出して突き合わせる（日付の再現性はビルド側の責務）。
    as_of = current_body.split("（", 1)[1].split(" 時点", 1)[0]
    expected_body = build_market_rate_markdown(skills, as_of=as_of).strip()

    assert current_body == expected_body, (
        "F02 の相場表が古い可能性があります。"
        " `python scripts/skill_catalog_tool.py build-market-rate` を実行してください。"
    )


def test_state_apply_table_excludes_resource_stats():
    """出血/破裂等の状態異常表に FP/MP/HP のリソース増減が混入しないこと。"""
    skills = load_skills()
    body = build_market_rate_markdown(skills, as_of="2000-01-01")
    section = body.split("### 状態異常の付与量相場", 1)[1].split("### 効果タイプ別の注意", 1)[0]
    for resource in ("| HP ", "| MP ", "| FP "):
        assert resource not in section, f"{resource.strip()} が状態異常表に混入している"
