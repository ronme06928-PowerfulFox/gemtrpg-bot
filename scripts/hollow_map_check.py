"""Exercise both views of the real Hollow route and capture the latest screenshot set."""

import argparse
import sys
from urllib.parse import urlencode
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, CONTRAST, ROOT, api, click, launch_and_verify, register
from scripts.hollow_run_check import command, create_owned, enter_room, library, resolve_round, wait_for


def verify(browser, *, seeded=False):
    suffix = uuid4().hex[:6]
    author = register(browser, "MapAuthor" + suffix, author=True)
    if not seeded:
        library(author, suffix)
    for row in api(author, "GET", "/api/units/tier")["entries"]:
        number = row["payload"].get("tier")
        if number in (1, 2):
            name = "入穴" if number == 1 else "浅層上部"
            api(author, "PUT", f"/api/units/tier/{row['entry_id']}", base_revision=row["revision"],
                visibility=row["visibility"], payload={**row["payload"], "name": name})
    host, player = [register(browser, name + suffix) for name in ("Rio", "Nagi")]
    room = "青晶坑の先遣隊 " + suffix
    code = api(host, "POST", "/api/hollow/rooms", room_name=room)["join_code"]
    api(player, "POST", "/api/join_room_by_code", room_name=room, join_code=code, play_mode="hollow")
    skill = api(host, "GET", "/api/get_skill_data")["Ps-01"]["チャットパレット"]
    owners = [(player, ["岩牙", "晶殻", "水鏡"]), (host, ["夜風", "蒼羽", "銀針", "蒼月"])]
    owned = {name: create_owned(page, name, skill, portrait="女冒険者" if i % 2 else "男冒険者")
             for page, names in owners for i, name in enumerate(names)}
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
        enter_room(page, room)
        expect(page.get_by_role("heading", name="出発前")).to_be_visible()
        for hidden in ("#dock-quick-edit-icon", "#dock-staging-icon", "#dock-add-char-icon"):
            expect(page.locator(hidden)).to_be_hidden()
        expect(page.get_by_role("button", name="パーティメンバーを追加", exact=True)).to_be_enabled()
    shot(host, "1280-dock.png")

    def picker(page):
        click(page, "パーティメンバーを追加")
        dialog = page.locator("#hollow-owned-window")
        expect(dialog.get_by_role("checkbox").first).to_be_visible()
        return dialog

    def add_characters(dialog, *names):
        for name in names:
            dialog.locator(".hollow-owned-row").filter(has_text=name).get_by_role("checkbox").check()

    dialog = picker(player)
    assert dialog.get_by_role("checkbox").count() == 3
    expect(dialog.locator(".hollow-owned-row").filter(has_text="岩牙")).to_contain_text("HP 150 · MP 50")
    add_characters(dialog, "岩牙", "晶殻")
    shot(player, "1280-add-selected.png")
    ratios += player.evaluate(CONTRAST, [[".hollow-owned-row strong", None],
        [".hollow-owned-stats", None], [".hollow-owned-row", "borderTopColor"]])
    dialog.get_by_role("button", name="追加", exact=True).click()
    expect(dialog).to_be_hidden()
    wait_for(state, lambda value: len(value["party"]["order"]) == 2)
    dialog = picker(player)
    expect(dialog.locator(".hollow-owned-row").filter(has_text="パーティにいます")).to_have_count(2)
    expect(dialog.locator(".hollow-owned-row").filter(has_text="岩牙").get_by_role("checkbox")).to_be_disabled()
    shot(player, "1280-add-in-party.png")
    dialog.get_by_role("button", name="閉じる").click()

    dialog = picker(host)
    add_characters(dialog, "夜風", "蒼羽", "銀針", "蒼月")
    dialog.get_by_role("button", name="追加", exact=True).click()
    expect(dialog).to_be_hidden()
    wait_for(state, lambda value: len(value["party"]["order"]) == 6)
    dialog = picker(player)
    expect(dialog).to_contain_text("空きがありません")
    expect(dialog.locator(".hollow-owned-row").filter(has_text="水鏡").get_by_role("checkbox")).to_be_disabled()
    expect(dialog.get_by_role("button", name="追加", exact=True)).to_be_disabled()
    shot(player, "1280-add-full.png")
    dialog.get_by_role("button", name="閉じる").click()

    def select_map(tier):
        title = "虚夢の辺縁へ降りる" if tier == 1 else "次のマップを選ぶ"
        expect(host.get_by_role("heading", name=title)).to_be_visible()
        expect(player.get_by_role("heading", name=title)).to_be_visible()
        choices = host.locator(".hollow-choice-card")
        expect(choices).to_have_count(2 if tier == 1 else 1)
        expect(player.locator(".hollow-choice-card:disabled")).to_have_count(choices.count())
        expect(player_map).to_contain_text("ホストがマップを選んでいます")
        expect(host.locator(".hollow-ribbon")).to_contain_text("ラン中 · マップ選択待ち")
        expect(host.locator("#dock-hollow-add")).to_be_disabled()
        assert state()["logs"][-1]["message"] == f"T{tier} のマップを選んでください"
        if tier == 1:
            shot(host, "1280-choice-host.png")
            shot(player, "1280-choice-player.png")
            player.set_viewport_size({"width": 680, "height": 900})
            cards = player.locator(".hollow-choice-card")
            assert cards.nth(1).bounding_box()["y"] > cards.first.bounding_box()["y"]
            shot(player, "680-choice.png")
            player.set_viewport_size({"width": 1280, "height": 860})
            player.reload()
            expect(player.get_by_role("heading", name=title)).to_be_visible()
            expect(player_curtain).to_be_hidden()
            spec = [[".hollow-choice h2", None], [".hollow-choice-description", None],
                    [".hollow-choice-card", "borderTopColor"]]
            if seeded:
                spec += [[".hollow-category", None], [".hollow-category", "borderTopColor"]]
            ratios.extend(host.evaluate(CONTRAST, spec))
            assert player.locator(".hollow-choice-card:disabled").first.evaluate("el => getComputedStyle(el).opacity") == "1"
            ratios.extend(player.evaluate(CONTRAST, spec))
        else:
            expect(host_map).to_contain_text("10F")
            expect(host_map).to_contain_text("を退けた")
            shot(host, "1280-choice-tier2.png")
        choice = choices.filter(has_text="青晶洞") if seeded and tier == 1 else choices.first
        name = choice.locator("strong").inner_text()
        if seeded and tier == 1:
            expect(choice.locator(".hollow-choice-art img")).to_be_visible()
            expect(choice.locator(".hollow-category")).to_have_text(["亀裂", "凝魔", "貫通"])
        choice.focus()
        choice.press("Enter")
        expect(host.locator("#app-dialog-title")).to_have_text("このマップへ進む")
        expect(host.locator("#app-dialog-backdrop")).to_have_attribute("data-theme", "abyss")
        if tier == 1:
            shot(host, "1280-choice-confirm.png")
            host.locator("#app-dialog-cancel").click()
            expect(choice).to_be_focused()
            choice.click()
        host.locator("#app-dialog-confirm").click()
        for curtain in (host_curtain, player_curtain):
            expect(curtain).to_contain_text(name)
            expect(curtain).to_contain_text(f"T{tier}")
        if tier == 1:
            shot(player, "1280-choice-curtain.png")
        expect(host_curtain).to_be_hidden()
        expect(player_curtain).to_be_hidden()
        assert state()["logs"][-1]["message"].endswith(f"が {name} を選んだ")
        return name

    click(host, "ランを始める")
    select_map(1)
    expect(host_map.get_by_role("heading", name="入穴")).to_be_visible()
    expect(player_map).to_contain_text("ホストが次のマスを選ぶ")
    assert len(state()["hollow"]["run"]["map"]["rows"]) == 3
    expect(player_map.get_by_role("button", name="撤退")).to_have_count(0)
    expect(player.locator(".hollow-node.is-next").first).to_have_attribute("aria-disabled", "true")
    chips = {char["owned_character_id"]: char["id"] for char in state()["characters"]}
    host.locator(f'[data-chip="{chips[owned["岩牙"]]}"]').click()
    host.locator(f'[data-chip="{chips[owned["銀針"]]}"]').click()
    expect(host.locator(".hollow-map-group").first).to_contain_text("銀針")
    expect(player.locator(".hollow-map-group").first).to_contain_text("銀針")

    for floor in range(1, 12):
        target = host.locator(".hollow-node.is-next:not([aria-disabled])").first
        if floor == 1:
            target.hover()
            expect(host.locator(".hollow-map-tip")).to_contain_text("押して入場")
            ratios += host.evaluate(CONTRAST, [[".hollow-map-tip b", None], [".hollow-map-tip", "borderTopColor"]])
            target.focus()
            target.press("Enter")
            expect(entry).to_be_visible()
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
        expect(host.locator("#map-viewport")).to_be_visible()
        expect(player.locator("#map-viewport")).to_be_visible()
        for _ in range(5):
            resolved = resolve_round(host, state, room)
            if resolved["combat_phase"] == "ready":
                break
        event = resolved["hollow"]["run"]["current_event"]
        assert event["outcome"] == "VICTORY"
        if resolved["hollow"]["run"].get("reward"):
            command(host, "hollow_choose_reward", floor=floor, relic_id=None)
        if floor == 9:
            command(host, "hollow_end_fusion", floor=floor)
        if floor == 1:
            expect(host_curtain).to_contain_text("制圧")
            expect(player_curtain).to_contain_text("制圧")
        if floor == 10:
            assert event["type"] == "boss" and (not seeded or "晶殻の群れ" in event["boss_name"])
            select_map(2)
            player.reload()
            expect(player_map.get_by_role("heading", name="浅層上部")).to_be_visible()
            expect(player_curtain).to_be_hidden()
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
            player.set_viewport_size({"width": 680, "height": 900})
            expect(player.locator(".hollow-node.is-now")).to_be_visible()
            player.wait_for_function("document.querySelector('#visual-battle-container').getBoundingClientRect().bottom <= innerHeight + 1")
            assert player_map.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
            assert player.locator(".hollow-map-tray").evaluate("el => el.scrollHeight <= el.clientHeight + 1")
            player.set_viewport_size({"width": 1280, "height": 860})
    expect(host_map.get_by_role("heading", name="浅層上部")).to_be_visible()
    expect(player_map).to_contain_text("T2 · 11〜20F")
    host_map.get_by_role("button", name="撤退").click()
    expect(host.locator("#app-dialog-title")).to_have_text("撤退")
    host.locator("#app-dialog-confirm").click()
    expect(player_map.get_by_role("heading", name="撤退")).to_be_visible()
    expect(host_map).to_contain_text("11F")
    expect(player_map).to_contain_text("銀針")
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
    parser.add_argument("--seeded", action="store_true", help="Use the library created by hollow_seed.py")
    args = parser.parse_args()
    images = launch_and_verify(args.app_python, exercise=lambda browser: verify(browser, seeded=args.seeded))
    output = ROOT / "_local/pr35_11_shots"
    output.mkdir(parents=True, exist_ok=True)
    for pattern in ("1280-*.png", "680-*.png"):
        for old in output.glob(pattern):
            if old.name not in images:
                old.unlink()
    for name, data in images.items():
        (output / name).write_bytes(data)
    print(f"Saved {len(images)} screenshots in {output}")
