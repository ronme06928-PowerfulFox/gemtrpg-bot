"""Exercise the built Hollow party UI with three accounts and photograph it."""

import argparse
import sys
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, CONTRAST, ROOT, click, launch_and_verify, register


def verify(browser):
    suffix = uuid4().hex[:6]
    owner, guest, viewer = [register(browser, name + suffix) for name in ("Rio", "Nagi", "Touka")]
    room = "青晶坑の先遣隊 " + suffix
    photos = {}
    errors = []

    def shot(page, filename):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        photos[filename] = page.screenshot(animations="disabled")

    for page in (owner, guest, viewer):
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/#menu")
        page.locator('[data-screen-card="dungeon"]').click()

    click(owner, "新しく作る")
    owner.get_by_label("部屋名", exact=True).fill(room)
    click(owner, "作成")
    receipt = owner.locator("#hollow-code-window")
    expect(receipt.get_by_role("heading")).to_have_text("部屋を作りました")
    code = receipt.locator(".hollow-code").inner_text()
    owner.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
    click(owner, "まとめて写す")
    assert owner.evaluate("navigator.clipboard.readText()") == f"部屋：{room}　参加コード：{code}"
    shot(owner, "1280-created.png")
    receipt.get_by_role("button", name="閉じる").click()

    for page in (guest, viewer):
        click(page, "参加コードで入る")
        page.get_by_label("部屋名", exact=True).fill(room)
        page.get_by_label("参加コード", exact=True).fill(code)
        click(page, "参加")
        expect(page.locator(".dungeon-room")).to_contain_text(room)
    for page in (owner, guest, viewer):
        click(page, "入る")
        expect(page.locator("#dock-hollow-party")).to_be_visible()
        expect(page.locator(".hollow-ribbon")).to_contain_text("Rio" + suffix)

    click(owner, "参加コード")
    expect(receipt.locator(".hollow-code")).to_have_text(code)
    receipt.get_by_role("button", name="閉じる").click()

    roster = ["岩牙", "晶殻", "夜風", "蒼羽", "銀針", "水鏡"]
    for index, name in enumerate(roster):
        portrait = "男冒険者" if index % 2 == 0 else "女冒険者"
        (owner, guest, viewer)[index % 3].evaluate(
            """({room, name, portrait}) => socket.emit('request_add_character', {room, charData: {
              name, type: 'ally', image: '/static/images/characters/' + portrait + '.png',
              hp: 30, maxHp: 36, mp: 12, maxMp: 14, states: [{name: 'FP', value: 2}], x: -1, y: -1
            }})""", {"room": room, "name": name, "portrait": portrait},
        )

    click(owner, "パーティ")
    click(viewer, "パーティ")
    party = owner.locator("#hollow-party-window")
    read_only = viewer.locator("#hollow-party-window")
    select = party.locator("select")
    expect(select.locator("option")).to_have_count(7)
    for name in roster:
        value = select.locator("option").filter(has_text=name).get_attribute("value")
        select.select_option(value)
        party.get_by_role("button", name="加える").click()
        expect(party.locator(".hollow-party-row").filter(has_text=name)).to_be_visible()
    expect(read_only.locator(".hollow-party-row")).to_have_count(6)
    reserve = party.locator('[data-party-group="reserve"]')
    sortie = party.locator('[data-party-group="sortie"]')
    expect(reserve.locator("li")).to_have_count(2)
    expect(sortie.locator("li")).to_have_count(4)

    row = party.locator(".hollow-party-row").filter(has_text="蒼羽")
    grip = row.locator(".hollow-party-grip")
    grip.press("ArrowDown")
    expect(reserve.locator("li").first).to_contain_text("蒼羽")
    expect(grip).to_be_focused()
    grip.drag_to(sortie.locator("li").first)
    expect(sortie.locator("li").first).to_contain_text("蒼羽")
    expect(read_only.locator('[data-party-group="sortie"] li').first).to_contain_text("蒼羽")
    shot(owner, "1280-party.png")

    ratios = owner.evaluate(CONTRAST, [
        ["#hollow-party-window h2", None], [".hollow-party-character strong", None],
        [".hollow-party-character span", None], [".hollow-party-tags span", None],
        [".hollow-party-grip", None], [".hollow-party-grip", "borderTopColor"],
        ['[data-party-action="detail"]', "borderTopColor"],
        ['[data-party-action="transfer"]', "borderTopColor"],
    ])
    assert not read_only.locator(".hollow-party-grip").count()
    assert not read_only.get_by_role("button", name="加える").count()
    assert not read_only.get_by_role("button", name="外す").count()
    assert not read_only.get_by_role("button", name="ホストを譲る").count()
    expect(read_only.locator(".hollow-party-row").filter(has_text="夜風").get_by_role("button", name="アイテム")).to_be_enabled()
    expect(read_only.locator(".hollow-party-row").filter(has_text="岩牙").get_by_role("button", name="アイテム")).to_be_disabled()
    expect(read_only.get_by_role("button", name="詳細")).to_have_count(6)
    shot(viewer, "1280-player.png")
    read_only.locator(".hollow-party-row").filter(has_text="夜風").get_by_role("button", name="アイテム").click()
    expect(viewer.locator("#item-modal-header")).to_contain_text("夜風")
    viewer.locator("#item-modal-header .close-btn").click()
    click(viewer, "パーティ")
    read_only.locator(".hollow-party-row").filter(has_text="岩牙").get_by_role("button", name="詳細").click()
    expect(viewer.locator("#char-modal-backdrop")).to_contain_text("岩牙")
    viewer.locator("#char-modal-backdrop").click(position={"x": 5, "y": 5})
    click(viewer, "パーティ")

    party.locator(".hollow-party-member").filter(has_text="Nagi" + suffix).get_by_role("button", name="ホストを譲る").click()
    expect(owner.locator("#app-dialog-title")).to_have_text("ホストを譲る")
    shot(owner, "1280-transfer.png")
    owner.locator("#app-dialog-confirm").click()
    expect(read_only.locator(".hollow-party-member").filter(has_text="Nagi" + suffix)).to_contain_text("ホスト")
    click(guest, "パーティ")
    guest_party = guest.locator("#hollow-party-window")
    expect(guest_party.locator(".hollow-party-grip")).to_have_count(6)
    guest_party.get_by_role("button", name="部屋を退出").click()
    guest.locator("#app-dialog-confirm").click()
    expect(guest.get_by_text("参加中の部屋はありません")).to_be_visible()
    expect(read_only.locator(".hollow-party-member").filter(has_text="Rio" + suffix)).to_contain_text("ホスト")
    expect(read_only.locator(".hollow-party-member").filter(has_text="Nagi" + suffix)).to_have_count(0)
    shot(owner, "1280-inherited.png")
    party.get_by_role("button", name="閉じる").click()
    shot(owner, "1280-ribbon.png")
    click(owner, "パーティ")
    owner.set_viewport_size({"width": 680, "height": 900})
    expect(party).to_be_visible()
    assert party.evaluate("node => node.scrollWidth <= node.clientWidth + 1")
    shot(owner, "680-party.png")

    party.get_by_role("button", name="閉じる").click()
    ratios += owner.evaluate(CONTRAST, [
        [".hollow-ribbon strong", None], [".hollow-ribbon span", None],
        [".hollow-ribbon .btn-set", None], [".hollow-ribbon .btn-set", "borderTopColor"],
    ])
    owner.locator("#home-portal-btn").click()
    owner.locator("#app-dialog-confirm").click()
    expect(owner.locator(".dungeon-room")).to_contain_text("ホスト Rio" + suffix)
    expect(owner.locator(".dungeon-room")).to_contain_text("蒼羽")
    assert not errors, errors
    assert all(ratio >= minimum for _, ratio, minimum in ratios), ratios
    for minimum in (4.5, 3):
        print(f"Contrast ≥{minimum}:1: minimum {min(ratio for _, ratio, threshold in ratios if threshold == minimum):.2f}:1")
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python, exercise=verify)
    output = ROOT / "_local/pr35_6_shots"
    output.mkdir(parents=True, exist_ok=True)
    for pattern in ("1280-*.png", "680-*.png"):
        for old in output.glob(pattern):
            if old.name not in photos:
                old.unlink()
    for filename, photo in photos.items():
        (output / filename).write_bytes(photo)
    print(f"Saved {len(photos)} images in {output}")
