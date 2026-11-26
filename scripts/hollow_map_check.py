"""Exercise both views of the real Hollow route and capture the latest screenshot set."""

import argparse
import sys
from urllib.parse import urlencode
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, CONTRAST, ROOT, api, click, launch_and_verify, register
from scripts.hollow_run_check import command, library, resolve_round


def verify(browser):
    suffix = uuid4().hex[:6]
    author = register(browser, "MapAuthor" + suffix, author=True)
    library(author, suffix)
    for row in api(author, "GET", "/api/units/tier")["entries"]:
        number = row["payload"].get("tier")
        if number in (1, 2):
            name = "入穴" if number == 1 else "浅層上部"
            api(author, "PUT", f"/api/units/tier/{row['entry_id']}", base_revision=row["revision"],
                visibility=row["visibility"], payload={**row["payload"], "name": name})
    host, player = [register(browser, name + suffix) for name in ("Rio", "Nagi")]
    ids = [api(page, "GET", "/api/get_session_user")["user_id"] for page in (host, player)]
    room = "青晶坑の先遣隊 " + suffix
    code = api(host, "POST", "/api/hollow/rooms", room_name=room)["join_code"]
    api(player, "POST", "/api/join_room_by_code", room_name=room, join_code=code, play_mode="hollow")
    skill = api(host, "GET", "/api/get_skill_data")["Ps-01"]["チャットパレット"]
    roster = [
        ("岩牙", "男冒険者"), ("晶殻", "女冒険者"), ("夜風", "男冒険者"),
        ("蒼羽", "女冒険者"), ("銀針", "男冒険者"), ("水鏡", "女冒険者"),
    ]
    allies = [{
        "id": f"ally-{index}", "name": name, "type": "ally", "owner_id": ids[index % 2],
        "hp": 150, "maxHp": 150, "mp": 50, "maxMp": 50, "x": -1, "y": -1,
        "states": [{"name": "FP", "value": 50}], "commands": skill,
        "params": [{"label": "物理補正", "value": 100}],
        "image": f"/static/images/characters/{face}.png",
    } for index, (name, face) in enumerate(roster)]
    api(host, "POST", "/save_room", room_name=room, state={
        "characters": allies, "combat_phase": "ready", "round": 0, "timeline": [], "logs": [],
    })
    errors, photos, ratios = [], {}, []
    host_map = host.locator("#hollow-map-view")
    player_map = player.locator("#hollow-map-view")
    host_curtain = host.locator("#hollow-map-curtain")
    player_curtain = player.locator("#hollow-map-curtain")
    entry = host.locator("dialog.hollow-map-entry")

    def shot(page, filename):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        photos[filename] = page.screenshot(animations="disabled")

    def state():
        return api(host, "GET", "/load_room?" + urlencode({"name": room}))

    for page in (host, player):
        page.on("pageerror", lambda error: errors.append(error.stack or str(error)))
        page.goto(BASE + "/#dungeon")
        page.locator(".dungeon-room").filter(has_text=room).get_by_role("button", name="入る").click()
        expect(page.get_by_role("heading", name="出発前")).to_be_visible()
    for char in allies:
        command(host, "hollow_party_change", action="add", char_id=char["id"])
    expect(player_map).to_contain_text("ホストの出発を待っています")
    expect(player_map.get_by_role("button", name="ランを始める")).to_have_count(0)
    expect(host_map).to_contain_text("銀針")
    shot(host, "1280-forming.png")
    ratios += host.evaluate(CONTRAST, [
        [".hollow-route-card h2", None], [".hollow-route-card p", None],
        [".hollow-route-card .primary", None], [".hollow-route-card .primary", "borderTopColor"],
    ])
    click(host, "ランを始める")
    expect(host_map.get_by_role("heading", name="入穴")).to_be_visible()
    expect(player_map).to_contain_text("ホストが次のマスを選ぶ")
    assert len(state()["hollow"]["run"]["map"]["rows"]) == 3
    expect(player_map.get_by_role("button", name="撤退")).to_have_count(0)
    expect(player.locator(".hollow-node.is-next").first).to_have_attribute("aria-disabled", "true")
    host.locator('[data-chip="ally-0"]').click()
    host.locator('[data-chip="ally-4"]').click()
    expect(host.locator(".hollow-map-group").first).to_contain_text("銀針")
    expect(player.locator(".hollow-map-group").first).to_contain_text("銀針")

    for floor in range(1, 11):
        target = host.locator(".hollow-node.is-next:not([aria-disabled])").first
        if floor == 1:
            target.hover()
            expect(host.locator(".hollow-map-tip")).to_contain_text("押して入場")
            shot(host, "1280-tip.png")
            ratios += host.evaluate(CONTRAST, [[".hollow-map-tip b", None], [".hollow-map-tip", "borderTopColor"]])
            target.focus()
            target.press("Enter")
            expect(entry).to_be_visible()
            shot(host, "1280-entry.png")
            ratios += host.evaluate(CONTRAST, [
                [".hollow-map-entry h2", None], [".hollow-map-entry .hollow-route-btn", None],
                [".hollow-map-entry .hollow-route-btn", "borderTopColor"],
            ])
            entry.get_by_role("button", name="キャンセル").click()
            expect(entry).to_be_hidden()
            assert state()["hollow"]["run"]["floor"] == 0
        target.click()
        expect(entry).to_contain_text(f"{floor}F")
        entry.get_by_role("button", name="入場").click()
        if floor == 1:
            expect(host_curtain).to_contain_text("1F")
            expect(player_curtain).to_contain_text(host_curtain.inner_text().splitlines()[-1])
            expect(player_curtain).to_be_visible()
            expect(player.locator(".fx-round-banner")).to_have_count(0)
            shot(player, "1280-descent.png")
        expect(host.locator("#map-viewport")).to_be_visible()
        expect(player.locator("#map-viewport")).to_be_visible()
        resolved = resolve_round(host, state, room)
        assert resolved["hollow"]["run"]["current_event"]["outcome"] == "VICTORY"
        if floor == 1:
            expect(host_curtain).to_contain_text("制圧")
            expect(player_curtain).to_contain_text("制圧")
        if floor == 10:
            expect(host_curtain).to_contain_text("T2")
            expect(player_curtain).to_contain_text("浅層上部")
        expect(host_map).to_be_visible()
        expect(host_curtain).to_be_hidden()
        expect(player_map).to_be_visible()
        expect(player_curtain).to_be_hidden()
        if floor == 1:
            expect(host.locator(".hollow-ribbon")).to_contain_text("ラン中 · T1 · 1F")
            expect(host.locator(".hollow-map-paths line").first).to_be_attached()
            ratios += host.evaluate(CONTRAST, [
                [".hollow-map-head h2", None], [".hollow-map-guide span", None],
                [".hollow-map-guide strong", None], [".hollow-node", None],
                [".hollow-node", "borderTopColor"], [".hollow-map-paths line", "stroke"],
                [".hollow-map-chip", None], [".hollow-map-chip", "borderTopColor"],
                [".hollow-map-fog", None],
            ])
            shot(host, "1280-host-map.png")
            shot(player, "1280-player-map.png")
            player.set_viewport_size({"width": 680, "height": 900})
            expect(player.locator(".hollow-node.is-now")).to_be_visible()
            player.wait_for_function("document.querySelector('#visual-battle-container').getBoundingClientRect().bottom <= innerHeight + 1")
            assert player_map.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
            assert player.locator(".hollow-map-tray").evaluate("el => el.scrollHeight <= el.clientHeight + 1")
            shot(player, "680-map.png")
            player.set_viewport_size({"width": 1280, "height": 860})
    expect(host_map.get_by_role("heading", name="浅層上部")).to_be_visible()
    expect(player_map).to_contain_text("T2 · 11〜20F")
    shot(host, "1280-tier2.png")
    host_map.get_by_role("button", name="撤退").click()
    expect(host.locator("#app-dialog-title")).to_have_text("撤退")
    host.locator("#app-dialog-confirm").click()
    expect(player_map.get_by_role("heading", name="撤退")).to_be_visible()
    expect(host_map).to_contain_text("10F")
    expect(player_map).to_contain_text("銀針")
    shot(player, "1280-result.png")
    for page in (host, player):
        click(page, "ダンジョンへ戻る")
        page.locator("#app-dialog-confirm").click()
        expect(page.locator(".dungeon-room").filter(has_text=room)).to_have_count(0)
    assert not errors, errors
    assert all(ratio >= minimum for _, ratio, minimum in ratios), ratios
    for minimum in (4.5, 3):
        print(f"Contrast ≥{minimum}:1: minimum {min(ratio for _, ratio, threshold in ratios if threshold == minimum):.2f}:1")
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    images = launch_and_verify(parser.parse_args().app_python, exercise=verify)
    output = ROOT / "_local/pr35_9_shots"
    output.mkdir(parents=True, exist_ok=True)
    for pattern in ("1280-*.png", "680-*.png"):
        for old in output.glob(pattern):
            if old.name not in images:
                old.unlink()
    for name, data in images.items():
        (output / name).write_bytes(data)
    print(f"Saved {len(images)} screenshots in {output}")
