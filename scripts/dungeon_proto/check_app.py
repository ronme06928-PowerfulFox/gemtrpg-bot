"""Check the built app with two accounts and photograph its dungeon lobby."""
import argparse
import re
import sys
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, CONTRAST, ROOT, click, launch_and_verify, register


def verify(browser):
    token = uuid4().hex[:8]
    owner = register(browser, "Rio" + token)
    guest = register(browser, "Nagi" + token)
    name = "青晶坑の先遣隊 " + token[:4]
    photos = {}
    errors = []

    def shot(page, filename):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        photos[filename] = page.screenshot(animations="disabled")

    for page in (owner, guest):
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/#menu")
        expect(page.locator('#menu-portal')).to_have_attribute("data-theme", "paper")
        if page is owner:
            shot(page, "1280-menu.png")
        page.locator('[data-screen-card="dungeon"]').click()
        expect(page.locator('#menu-portal')).to_have_attribute("data-theme", "abyss")
        expect(page.get_by_role("heading", name="虚夢の辺縁")).to_be_visible()
        expect(page.get_by_text("参加中の部屋はありません")).to_be_visible()
    shot(owner, "1280-empty.png")
    ratios = owner.evaluate(CONTRAST, [
        [".dungeon-heading h2", None], [".dungeon-empty p", None],
        [".dungeon-empty .dungeon-primary", None],
        [".dungeon-empty .dungeon-primary", "borderTopColor"],
        [".dungeon-empty [data-action=join]", None],
        [".dungeon-empty [data-action=join]", "borderTopColor"],
        [".screen-back", "borderTopColor"],
    ])

    click(owner, "新しく作る")
    create = owner.locator(".dungeon-dialog")
    expect(create.get_by_label("参加コード")).to_be_hidden()
    create.get_by_label("部屋名").fill(name)
    ratios += owner.evaluate(CONTRAST, [["#dungeon-room-name", None], ["#dungeon-room-name", "borderTopColor"]])
    shot(owner, "1280-create.png")
    click(owner, "作成")
    receipt = owner.locator("#hollow-code-window")
    expect(receipt).to_contain_text("部屋を作りました")
    code = receipt.locator(".hollow-code").inner_text()
    shot(owner, "1280-issued-code.png")
    receipt.get_by_role("button", name="閉じる").click()
    owner_card = owner.locator(".dungeon-room")
    expect(owner_card).to_contain_text(name)
    expect(owner_card).to_contain_text("パーティを組んでいる")

    click(guest, "参加コードで入る")
    join = guest.locator(".dungeon-dialog")
    join.get_by_label("部屋名").fill(name)
    join.get_by_label("参加コード").fill("WRONG")
    click(guest, "参加")
    expect(join.get_by_role("alert")).to_have_text("参加コードが正しくありません")
    ratios += guest.evaluate(CONTRAST, [[".dungeon-dialog .screen-error", None]])
    shot(guest, "1280-join-error.png")
    join.get_by_label("参加コード").fill(code)
    click(guest, "参加")
    card = guest.locator(".dungeon-room")
    expect(card).to_contain_text(name)
    expect(card.get_by_role("button", name="削除")).to_have_count(0)
    expect(card.locator(".dungeon-tier")).to_have_count(5)
    ratios += guest.evaluate(CONTRAST, [
        [".dungeon-room .room-list-name", None], [".room-list-desc", None],
        [".dungeon-tier", None], [".dungeon-room .dungeon-primary", "borderTopColor"],
    ])
    shot(guest, "1280-joined.png")

    click(guest, "入る")
    expect(guest.locator("#main-app-container")).to_be_visible()
    expect(guest.locator("#header-attribute")).to_have_text("Player")
    expect(guest.locator("#current-room-name")).to_contain_text(name)
    expect(guest.locator("#home-portal-btn")).to_have_attribute("title", "ダンジョンに戻る")
    shot(guest, "1280-in-room.png")
    guest.locator("#home-portal-btn").click()
    expect(guest.locator("#app-dialog-title")).to_have_text("ダンジョンへ戻る")
    guest.locator("#app-dialog-confirm").click()
    expect(card).to_contain_text(name)
    expect(guest).to_have_url(re.compile(r"#dungeon$"))
    expect(guest.locator(".app-notice")).to_have_count(0, timeout=10000)
    shot(guest, "1280-returned.png")

    click(guest, "入る")
    expect(guest.locator("#main-app-container")).to_be_visible()
    guest.go_back()
    expect(guest.locator("#app-dialog-title")).to_have_text("ダンジョンへ戻る")
    guest.locator("#app-dialog-confirm").click()
    expect(card).to_contain_text(name)
    expect(guest).to_have_url(re.compile(r"#dungeon$"))
    guest.set_viewport_size({"width": 680, "height": 900})
    shot(guest, "680-dungeon.png")

    click(owner, "入る")
    expect(owner.locator("#header-attribute")).to_have_text("Player")
    owner.locator("#user-settings-btn").click()
    owner.locator("#chooser-room").click()
    expect(receipt.locator(".hollow-code")).to_have_text(code)
    receipt.get_by_role("button", name="閉じる").click()
    owner.locator("#home-portal-btn").click()
    owner.locator("#app-dialog-confirm").click()
    click(owner, "削除")
    expect(owner.locator("#app-dialog-title")).to_have_text("ルーム削除")
    owner.locator("#app-dialog-confirm").click()
    expect(owner.get_by_text("参加中の部屋はありません")).to_be_visible()
    assert not errors, errors
    assert all(ratio >= minimum for _, ratio, minimum in ratios), ratios
    for minimum in (4.5, 3):
        print(f"Contrast ≥{minimum}:1: minimum {min(ratio for _, ratio, threshold in ratios if threshold == minimum):.2f}:1")
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python, exercise=verify)
    output = ROOT / "_local/pr35_5_shots"
    output.mkdir(parents=True, exist_ok=True)
    for width in (1280, 680):
        for old in output.glob(f"{width}-*.png"):
            if old.name not in photos:
                old.unlink()
    for filename, photo in photos.items():
        (output / filename).write_bytes(photo)
    print(f"Saved {len(photos)} images in {output}")
