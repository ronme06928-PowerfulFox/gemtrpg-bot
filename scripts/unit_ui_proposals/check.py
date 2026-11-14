"""Standalone unit workspace preview checks with installed Chrome."""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
PREVIEW = ROOT / "_local" / "unit_ui_proposals" / "index.html"


def within_viewport(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    for selector in (".index-list", ".editor", ".inspector", ".candidate-list", ".candidate-detail"):
        for panel in page.locator(selector).all():
            if panel.is_visible():
                assert panel.evaluate("(el) => el.scrollWidth <= el.clientWidth + 1"), selector


def exercise(page):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(PREVIEW.as_uri())
    expect(page.get_by_role("heading", name="ユニット管理", exact=True)).to_be_visible()
    for proposal in ("台帳", "シート"):
        page.get_by_role("button", name=proposal, exact=True).click()
        page.locator(".index-filters").get_by_role("button", name="非公開", exact=True).click()
        rows = page.locator(".index-record")
        assert rows.count() > 1
        for row in rows.all():
            assert row.evaluate("""row => [...row.querySelectorAll(".badge")].every(badge =>
                badge.getBoundingClientRect().bottom <= row.getBoundingClientRect().bottom)""")
        page.locator(".index-filters").get_by_role("button", name="全件", exact=True).click()
        page.get_by_role("button", name="パラメータ", exact=True).click()
        value = page.get_by_label("筋力", exact=True)
        expect(value).to_be_visible()
        value.fill("25")
        page.get_by_role("button", name="スキル", exact=True).click()
        page.get_by_role("button", name="スキルを追加", exact=True).click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        dialog.get_by_label("候補を検索").fill("猛攻の輝き")
        dialog.get_by_role("button", name="補助", exact=True).click()
        expect(dialog.get_by_text("B-01", exact=True).first).to_be_visible()
        for label in ("パレット", "コスト", "効果", "特記"):
            expect(dialog.get_by_text(label, exact=True)).to_be_visible()
        within_viewport(page)
        alternate = "シート" if proposal == "台帳" else "台帳"
        page.get_by_role("button", name=alternate, exact=True).click()
        expect(dialog.get_by_label("候補を検索")).to_have_value("猛攻の輝き")
        page.get_by_role("button", name=proposal, exact=True).click()
        dialog.get_by_role("button", name="追加", exact=True).click()
        expect(dialog).to_be_hidden()
        skill = page.locator(".editor .linked-row").filter(has_text="猛攻の輝き")
        skill.get_by_role("button", name="外す", exact=True).click()
        expect(skill).to_have_count(0)
        page.get_by_role("button", name="パラメータ", exact=True).click()
        expect(value).to_have_value("25")
        within_viewport(page)
        page.get_by_role("button", name="編成", exact=False).filter(has=page.locator(".tab-count")).click()
        page.get_by_role("button", name="メンバー", exact=True).click()
        page.get_by_role("button", name="メンバーを追加", exact=True).click()
        expect(dialog).to_be_visible()
        page.keyboard.press("Escape")
        expect(dialog).to_be_hidden()
        within_viewport(page)
        page.get_by_role("button", name="ステージ", exact=False).filter(has=page.locator(".tab-count")).click()
        page.get_by_role("button", name="編成", exact=True).click()
        page.get_by_role("button", name="敵編成を選択", exact=True).click()
        expect(dialog).to_be_visible()
        dialog.get_by_role("button", name="閉じる", exact=True).click()
        page.get_by_role("button", name="フィールド効果", exact=True).click()
        expect(page.get_by_label("効果名", exact=True).first).to_have_value("冷たい空気")
        within_viewport(page)
        page.get_by_role("button", name="ユニット", exact=False).filter(has=page.locator(".tab-count")).click()
    page.get_by_role("button", name="新規作成").click()
    page.get_by_label("名称", exact=True).first.fill("新規試作ユニット")
    page.get_by_role("button", name="保存", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("試作内で保存済み")
    within_viewport(page)
    assert not errors, errors


if __name__ == "__main__":
    assert PREVIEW.exists(), "Run node scripts/unit_ui_proposals/build.mjs first."
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        for width in (1280, 680):
            exercise(browser.new_page(viewport={"width": width, "height": 900}))
            print(f"{width}px OK")
