"""Check the live reward and fusion UI with two browser sessions and a disposable seed DB."""
import argparse
import json
import sys
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, CONTRAST, ROOT, api, click, launch_and_verify, register
from scripts.hollow_run_check import command, create_owned, enter_room, resolve_round, wait_for


def verify_workspace(page, token, shot):
    page.goto(BASE + "/#hollow-data")
    section = page.locator(".unit-section")
    active = {}
    definitions = {row["entry_id"]: row for row in api(page, "GET", "/api/units/relic?domain=hollow")["entries"]}
    a = next(row for row in definitions.values() if row["payload"]["name"] == "試遊 血に濡れた手袋")
    api(page, "PUT", f"/api/units/relic/{a['entry_id']}", base_revision=a["revision"], visibility=a["visibility"],
        payload={**a["payload"], "flavor": "坑道に残された手袋。傷を覆っていた布に残った血を見て、奥に潜む敵の足取りを知る。\n" * 12})
    stages = api(page, "GET", "/api/units/hollow_load_stage?domain=hollow")["entries"]

    def archived_threshold():
        return max(row["payload"]["threshold"] for row in stages) + 150

    for kind in ("hollow_buff", "relic", "hollow_load_stage", "hollow_recipe", "hollow_item"):
        page.locator(f'.unit-tabs [data-kind="{kind}"]').click()
        click(page, "＋ 新規")
        name = f"確認 {kind} {token}"
        section.locator('[data-path="name"],[data-field="name"]').fill(name)
        if kind == "hollow_buff":
            section.locator('[data-field="description"]').fill("的中時、相手の出血＋1。")
            section.locator('[data-field="effect"]').fill(json.dumps({"effects": [
                {"timing": "HIT", "type": "APPLY_STATE", "target": "target", "state_name": "出血", "value": 1},
            ]}, ensure_ascii=False))
        if kind in ("relic", "hollow_load_stage"):
            section.locator('[data-path="buff_id"]').select_option(active["hollow_buff"])
        if kind == "relic":
            section.locator('[data-path="category"]').select_option("出身強化")
            section.locator('[data-path="target.type"]').select_option("nth")
            section.locator('[data-path="target.n"]').fill("2")
        elif kind == "hollow_load_stage":
            section.locator('[data-path="threshold"]').fill(str(archived_threshold()))
        elif kind == "hollow_recipe":
            section.locator('[data-path="material_ids.0"]').select_option(a["entry_id"])
            section.locator('[data-path="material_ids.1"]').select_option(active["relic"])
            section.locator('[data-path="result_id"]').select_option(active["relic"])
        elif kind == "hollow_item":
            section.locator('[data-field="effect"]').fill(json.dumps({"type":"buff","buff_id":active["hollow_buff"]}))
        with page.expect_response(lambda reply: reply.request.method == "POST"
                                  and urlsplit(reply.url).path == f"/api/units/{kind}") as saved:
            click(page, "保存")
        assert saved.value.status == 201, saved.value.text()
        active[kind] = saved.value.json()["entry"]["entry_id"]
        click(page, "再読み込み")
        expect(section.locator('[data-path="name"],[data-field="name"]')).to_have_value(name)
        shot(page, f"1280-data-{kind}.png")
    expect(page.locator('.unit-tabs button', has_text="ドロップ表")).to_be_disabled()
    stage_id = active["hollow_load_stage"]
    saved_stage = api(page, "GET", f"/api/units/hollow_load_stage/{stage_id}")
    api(page, "POST", f"/api/units/hollow_load_stage/{stage_id}/deprecation", deprecated=True,
        base_revision=saved_stage["revision"])
    return active


def verify(browser):
    token = uuid4().hex[:7]
    photos, ratios, errors = {}, [], []

    def shot(page, name):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), name
        photos[name] = page.screenshot(animations="disabled")

    author = register(browser, "RelicEditor" + token, author=True)
    author.on("pageerror", lambda error: errors.append(str(error)))
    created = verify_workspace(author, token, shot)
    recipe = next(row["payload"] for row in api(author, "GET", "/api/units/hollow_recipe?domain=hollow")["entries"]
                  if row["payload"]["name"] == "試遊 血脈の指輪")
    host, player = [register(browser, label + token) for label in ("RelicHost", "RelicGuest")]
    room = "淵遺物試遊 " + token
    code = api(host, "POST", "/api/hollow/rooms", room_name=room)["join_code"]
    api(player, "POST", "/api/join_room_by_code", room_name=room, join_code=code, play_mode="hollow")
    for page in (host, player):
        page.emulate_media(reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        enter_room(page, room)
    skill = api(host, "GET", "/api/get_skill_data")["Ps-01"]["チャットパレット"]
    members = [create_owned(host, name, skill, hp=260, strength=150) for name in ("夜風","蒼羽","銀針","水鏡")]
    command(host, "hollow_party_add_owned", owned_ids=members)

    def state():
        return api(host, "GET", "/load_room?" + urlencode({"name": room}))

    def run():
        return state()["hollow"]["run"]

    def select_map(name):
        host.locator('button[data-map-id]').filter(has_text=name).click()
        click(host, "進む")
        wait_for(run, lambda current: not current.get("map_candidates"))

    def rewards():
        expect(host.get_by_role("heading", name="戦闘の報酬")).to_be_visible()
        expect(player.get_by_text("ホストが選んでいます")).to_be_visible()
        expect(player.get_by_role("button", name="見送る", exact=True)).to_have_count(0)
        expect(host.locator(".fx-round-banner")).to_be_hidden()
        expect(player.locator(".fx-round-banner")).to_be_hidden()

    def inventory(short, long):
        click(player, "淵遺物")
        dialog = player.locator("dialog.hr-dialog")
        expect(dialog).to_be_visible()
        dialog.locator(f'[data-key="{short}"]').click()
        short_box = dialog.bounding_box()
        shot(player, "1280-inventory-short.png")
        dialog.locator(f'[data-key="{long}"]').click()
        expect(dialog.locator(".hr-flavor")).to_contain_text("坑道に残された手袋")
        assert dialog.bounding_box() == short_box
        shot(player, "1280-inventory-long.png")
        ratios.extend(player.evaluate(CONTRAST, [
            [".hr-detail h3", None], [".hr-detail .hr-effect", None], [".hr-detail .hr-flavor", None],
            [".hr-load-bar", "borderTopColor"], [".hr-icon[aria-pressed=true]", "borderTopColor"],
        ]))
        player.set_viewport_size({"width": 680, "height": 800})
        assert dialog.bounding_box()["width"] < 680
        shot(player, "680-inventory.png")
        player.set_viewport_size({"width": 1280, "height": 860})
        dialog.get_by_role("button", name="閉じる").click()

    def fusion():
        expect(host.get_by_role("heading", name="虚夢変転")).to_be_visible()
        expect(player.get_by_role("heading", name="虚夢変転")).to_be_visible()
        expect(player.get_by_text("ホストが選んでいます")).to_be_visible()
        expect(player.get_by_role("button", name="変転する")).to_have_count(0)
        current = run()
        protected = set(recipe["material_ids"])
        assert protected <= set(current["relics"]), "試遊の抽選で合成材料が揃いませんでした"
        common = [key for key in current["relics"] if key not in protected]
        common.extend(rank for rank, count in current["materials"].items() for _ in range(count))
        assert len(common) >= 4

        def add(keys):
            for key in keys:
                action = "add" if key.startswith("HR-") else "material"
                host.locator(f'[data-relic-action="{action}"][data-key="{key}"]').click()

        add(common[:2])
        expect(host.locator(".hr-forecast")).to_contain_text("%")
        shot(host, "1280-fusion-forecast.png")
        click(host, "変転する")
        expect(host.locator(".hr-result")).to_be_visible()
        add(recipe["material_ids"])
        expect(host.locator(".hr-forge-controls .hr-omen")).to_be_visible()
        expect(host.locator("[data-relic-wish]")).to_have_count(0)
        shot(host, "1280-fusion-omen.png")
        click(host, "変転する")
        expect(host.locator(".hr-result")).to_contain_text("特別な組み合わせを見つけた")
        expect(host.locator(".hr-discoveries")).to_contain_text("血脈の指輪")
        expect(player.locator(".hr-discoveries")).not_to_contain_text("血脈の指輪")
        host.locator(".hr-discoveries").scroll_into_view_if_needed()
        shot(host, "1280-fusion-result.png")
        add(common[2:4])
        host.locator("[data-relic-wish]").check()
        host.locator('[data-relic-action="wish"][data-key="斬撃"]').click()
        expect(host.locator(".hr-forecast")).to_contain_text("100%")
        shot(host, "1280-fusion-wish.png")
        click(host, "変転する")
        wait_for(run, lambda current: current["fusion"]["wishes_left"] == 0)
        expect(host.locator(".hr-result")).to_contain_text("斬撃")
        click(host, "変転を終えてボスへ")

    click(host, "ランを始める")
    select_map("青晶洞")
    recorded = []
    duplicated = False
    for floor in range(1, 12):
        host.locator(".hollow-node.is-next:not([aria-disabled])").first.click()
        click(host, "入場")
        wait_for(state, lambda snapshot: snapshot["combat_phase"] == "active")
        for _ in range(7):
            if resolve_round(host, state, room)["combat_phase"] == "ready":
                break
        rewards()
        current = run()
        assert all(card["effect_text"] for card in current["reward"]["cards"])
        if floor == 1:
            shot(host, "1280-reward-host.png")
            shot(player, "1280-reward-player.png")
            ratios.extend(host.evaluate(CONTRAST, [
                [".hr-reward-card h3", None], [".hr-reward-card .hr-effect", None],
                [".hr-load-up", None], [".hr-reward-card", "borderTopColor"],
            ]))
        candidates = current["reward"]["relic_ids"]
        missing = set(recipe["material_ids"]) - set(current["relics"])
        selected = next((key for key in candidates if key in missing), None)
        if floor == 1:
            selected = None
            click(host, "見送る")
        else:
            if selected is None and not duplicated and floor >= 4:
                selected = next((key for key in candidates if key in current["relics"]), None)
            selected = selected or next((key for key in candidates if key not in current["relics"]), candidates[0])
            duplicated |= selected in current["relics"]
            host.locator(f'[data-relic-action="select"][data-key="{selected}"]').click()
            click(host, "受け取る")
        wait_for(run, lambda current: not current.get("reward"))
        recorded.append((floor, selected))
        if floor == 9:
            assert duplicated
            long = recipe["material_ids"][0]
            assert any(row["id"] == long and row["flavor"] for row in run()["relic_cards"])
            inventory(next(key for key in run()["relics"] if key != long), long)
            fusion()
        if floor == 10:
            select_map("古い晶脈")
    assert any("報酬を見送った" in row["message"] for row in state()["logs"])
    assert any("所持済み。素材" in row["message"] for row in state()["logs"])
    assert any("を手に入れた" in row["message"] for row in state()["logs"])
    assert not errors, errors
    assert all(ratio >= wanted for _, ratio, wanted in ratios), ratios
    print(json.dumps({"created": created, "visited": recorded, "contrast": ratios}, ensure_ascii=False))
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python, exercise=verify)
    out = ROOT / "_local/pr35_14_shots"
    out.mkdir(parents=True, exist_ok=True)
    for name, data in photos.items():
        (out / name).write_bytes(data)
