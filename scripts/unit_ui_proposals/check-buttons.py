"""Exercise the three Plan 61 comparison scenarios in Chrome."""

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


PREVIEW = Path(__file__).resolve().parents[2] / "_local" / "unit_ui_proposals" / "buttons.html"


def exercise(page):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(PREVIEW.as_uri())
    action = lambda key: page.locator(f".unit-workspace [data-unit-action='{key}']")
    skills = page.locator('[data-section="skills"]')
    section = page.locator(".unit-editor" if page.viewport_size["width"] == 680 else ".unit-section")
    old = page.get_by_role("button", name="今の形", exact=True)
    new = page.get_by_role("button", name="新しい形", exact=True)
    dialog = page.locator(".unit-dialog")
    expect(page.locator(".unit-skill-row")).to_have_count(18)
    page.locator('[data-section="basic"]').click()
    name = page.locator('input[data-path="name"]')
    original = name.input_value()
    name.fill("試作変更")
    skills.click()
    expect(page.locator(".unit-skill-row")).to_have_count(18)
    new.click()
    expect(action("discard")).to_be_enabled()
    action("reload").click()
    expect(page.locator("#app-dialog-cancel")).to_be_focused()
    page.keyboard.press("Enter")
    expect(action("discard")).to_be_enabled()
    page.locator('[data-section="basic"]').click()
    expect(name).to_have_value("試作変更")
    action("record").first.click()
    expect(page.locator("#app-dialog-cancel")).to_be_focused()
    page.keyboard.press("Enter")
    expect(name).to_have_value("試作変更")
    action("discard").click()
    page.locator("#app-dialog-confirm").click()
    expect(name).to_have_value(original)
    expect(action("discard")).to_be_disabled()
    action("more").click()
    expect(action("delete")).to_be_disabled()
    expect(page.get_by_text("編成で使用中", exact=True)).to_be_visible()
    action("more").click()
    skills.click()
    section.evaluate("(el) => el.scrollTop = 500")
    add = page.locator('[data-source="skill"]')
    last_skill = page.locator(".unit-skill-row").nth(16)
    last_skill.locator('[data-unit-action="rename-skill"]').click()
    dialog.locator("[data-skill-name]").fill("試作スキル名")
    dialog.get_by_role("button", name="適用", exact=True).click()
    expect(last_skill.get_by_text("試作スキル名", exact=True)).to_be_visible()
    assert add.evaluate("""button => {
        const box = button.getBoundingClientRect();
        const panel = button.closest('.unit-editor').getBoundingClientRect();
        return box.top >= panel.top && box.bottom <= panel.bottom;
    }""")
    add.click()
    search = dialog.locator("[data-candidate-search]")
    search.fill("Pb-")
    dialog.get_by_role("button", name="Pb", exact=True).click()
    candidate_scroll = dialog.locator(".unit-candidate-scroll")
    for skill_id in ("Pb-03", "Pb-04", "Pb-05"):
        candidate = dialog.locator(f'.unit-candidate:has([data-id="{skill_id}"])')
        candidate.locator('button[data-unit-action="candidate"]').scroll_into_view_if_needed()
        position = candidate_scroll.evaluate("(el) => el.scrollTop")
        candidate.locator('button[data-unit-action="candidate"]').click()
        expect(candidate.get_by_text("追加済み", exact=True)).to_be_visible()
        expect(search).to_have_value("Pb-")
        expect(dialog.get_by_role("button", name="Pb", exact=True)).to_have_attribute("aria-pressed", "true")
        assert candidate_scroll.evaluate("(el) => el.scrollTop") == position
    action("close-dialog").click()
    old.click()
    expect(page.locator(".unit-skill-row")).to_have_count(21)
    for skill_id in ("B-01", "B-02", "B-03"):
        add.click()
        search = dialog.locator("[data-candidate-search]")
        expect(search).to_have_value("")
        search.fill(skill_id)
        dialog.locator(f'[data-id="{skill_id}"]').click()
        expect(dialog).to_be_hidden()
    action("tab").and_(page.locator('[data-kind="formation"]')).click()
    page.locator("#app-dialog-confirm").click()
    action("record").first.click()
    page.locator('[data-section="members"]').click()
    for _ in range(2):
        page.locator('[data-path="members"][data-unit-action="picker"]').click()
        dialog.locator('.unit-candidate').first.locator('[data-unit-action="candidate"]').click()
        expect(dialog).to_be_hidden()
    new.click()
    page.locator('[data-path="members"][data-unit-action="picker"]').click()
    member = dialog.locator('.unit-candidate').first
    for _ in range(2):
        member.locator('[data-unit-action="candidate"]').click()
    expect(member.get_by_text("追加 2 回", exact=True)).to_be_visible()
    action("close-dialog").click()
    action("transfer").click()
    for tab in ("取り込み", "書き出し"):
        dialog.get_by_role("button", name=tab, exact=True).click()
        expect(dialog.locator(".cat-primary:visible")).to_have_count(1)
    dialog.get_by_role("button", name="取り込み", exact=True).click()
    fixture = {"entries": [{"kind": "unit", "entry_id": "U-777", "payload": {"name": "取り込み試験"}}]}
    dialog.locator('[data-unit-file="package"]').set_input_files({
        "name": "fixture.json", "mimeType": "application/json", "buffer": json.dumps(fixture).encode(),
    })
    expect(dialog.locator(".buttons-dialog-footer .cat-primary:visible")).to_have_attribute("data-unit-action", "confirm-package")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    action("close-dialog").click()
    action("tab").and_(page.locator('[data-kind="stage"]')).click()
    page.locator("#app-dialog-confirm").click()
    action("record").first.click()
    for path in ("concept", "description"):
        control = page.locator(f'.unit-section [data-path="{path}"]')
        assert control.evaluate("""el => {
            const field = el.closest('label').getBoundingClientRect();
            const input = el.getBoundingClientRect();
            return input.width >= field.width * 0.8 && input.right <= field.right + 1;
        }"""), path
    assert not errors, errors


if __name__ == "__main__":
    assert PREVIEW.exists(), "Run build-buttons.mjs first."
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        for width in (1280, 680):
            exercise(browser.new_page(viewport={"width": width, "height": 760}))
            print(f"{width}px OK")
