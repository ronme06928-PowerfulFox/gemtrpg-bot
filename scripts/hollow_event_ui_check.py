"""Verify PR35-16 with two browser sessions and a disposable seeded DB."""

import argparse
import sys
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, CONTRAST, ROOT, api, click, launch_and_verify, register
from scripts.hollow_run_check import command, enter_room, resolve_round
from scripts.hollow_seed import PREFIX

VIEW = "#hollow-map-view"
OUT = ROOT / "_local/pr35_16_shots"


def field(page, path):
    return page.locator(f'.unit-section [data-path="{path}"]')


def entry(page, kind, entry_id):
    page.locator(f'.unit-tabs [data-kind="{kind}"]').click()
    page.locator(f'.unit-records [data-id="{entry_id}"]').click()
    expect(page.locator(".unit-detail-header .cat-id")).to_have_text(entry_id)


def new_entry(page, kind, name):
    page.locator(f'.unit-tabs [data-kind="{kind}"]').click()
    click(page, "＋ 新規")
    field(page, "name").fill(name)


def save(page, kind, entry_id=None):
    path = f"/api/units/{kind}" + (f"/{entry_id}" if entry_id else "")
    method = "PUT" if entry_id else "POST"
    with page.expect_response(lambda response: response.request.method == method
                              and urlsplit(response.url).path == path) as response:
        click(page, "保存")
    assert response.value.status == (200 if entry_id else 201), response.value.text()
    record = response.value.json()["entry"]
    expect(page.locator(".unit-detail-header .cat-id")).to_have_text(record["entry_id"])
    expect(page.locator(".unit-dirty")).to_have_text("")
    return record


def shot(photos, page, name):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    photos[name + ".png"] = page.screenshot(animations="disabled")


def edit_library(page, photos):
    rows = api(page, "GET", "/api/units?domain=hollow")["entries"]
    item = next(row["entry_id"] for row in rows if row["kind"] == "hollow_item")
    relic = next(row["entry_id"] for row in rows if row["kind"] == "relic" and row["payload"]["name"] == f"{PREFIX} 血脈の指輪")
    area = next(row["entry_id"] for row in rows if row["payload"]["name"] == f"{PREFIX} 青晶洞")
    page.goto(BASE + "/#hollow-data")

    new_entry(page, "hollow_event", "薄明の泉")
    field(page, "text").fill("水面に石灯が揺れる。")
    field(page, "choices.0.label").fill("光を調べる")
    field(page, "choices.0.check").select_option("yes")
    field(page, "choices.0.skill").select_option("五感")
    field(page, "choices.0.difficulty").fill("14")
    field(page, "choices.0.effect.kind").select_option("relic")
    field(page, "choices.0.effect.id").select_option(relic)
    click(page, "＋ 選択肢を追加")
    field(page, "choices.1.label").fill("光をすくう")
    field(page, "choices.1.effect.kind").select_option("item")
    field(page, "choices.1.effect.id").select_option(item)
    click(page, "＋ 選択肢を追加")
    field(page, "choices.2.label").fill("やり過ごす")
    event = save(page, "hollow_event")["entry_id"]
    shot(photos, page, "1280-イベント編集")

    new_entry(page, "drop_table", "灯のドロップ")
    click(page, "＋ 行を追加")
    field(page, "rows.0.id").select_option(item)
    click(page, "＋ 行を追加")
    field(page, "rows.1.kind").select_option("relic")
    field(page, "rows.1.id").select_option(relic)
    expect(page.locator("[data-encounter-share]").first).to_have_text("50%")
    table = save(page, "drop_table")["entry_id"]
    shot(photos, page, "1280-ドロップ表編集")

    new_entry(page, "treasure_chest", "灯の箱")
    field(page, "text").fill("石灯のそばに置かれた箱。")
    field(page, "drop_table_id").select_option(table)
    expect(page.get_by_text("中身の割合", exact=True)).to_be_visible()
    expect(page.get_by_text("50%", exact=False)).to_have_count(2)
    chest = save(page, "treasure_chest")["entry_id"]
    shot(photos, page, "1280-宝箱編集")

    entry(page, "hollow_map", area)
    page.locator('.unit-toc [data-section="events"]').click()
    field(page, "events.0.weight").fill("0")
    field(page, "events.1.weight").fill("0")
    field(page, "chests.0.weight").fill("0")
    click(page, "＋ 魔素だまりを追加")
    field(page, "events.2.event_id").select_option(event)
    click(page, "＋ 宝箱を追加")
    field(page, "chests.1.chest_id").select_option(chest)
    save(page, "hollow_map", area)
    shot(photos, page, "1280-マップのイベント表")
    page.reload()
    expect(page.get_by_role("button",name="＋ 新規",exact=True)).to_be_visible()
    for kind, key, path, value in (("hollow_event", event, "choices.0.skill", "五感"),
                                    ("drop_table", table, "rows.1.id", relic),
                                    ("treasure_chest", chest, "drop_table_id", table),
                                    ("hollow_map", area, "chests.1.chest_id", chest)):
        entry(page, kind, key)
        if kind == "hollow_map":
            page.locator('.unit-toc [data-section="events"]').click()
        expect(field(page, path)).to_have_value(value)


def make_owned(page, name, level):
    skill = api(page, "GET", "/api/get_skill_data")["Ps-01"]["チャットパレット"]
    data = {"name": name, "commands": skill,
            "status": [{"label": key, "value": hp, "max": hp} for key, hp in (("HP",180),("MP",50),("FP",50))],
            "params": [{"label":"五感","value":level},{"label":"物理補正","value":200}]}
    return api(page,"POST","/api/owned_characters",data=data)["character"]["id"]


def close_result(page):
    control = page.locator(f"{VIEW} [data-event-action=close]")
    if control.count():
        control.click()


def choose_node(page, run, wanted):
    layout = run["map"]
    nodes = {node["id"]:node for row in layout["rows"] for node in row}
    current = nodes[layout["current"]]

    def matches(kind):
        return int(kind in wanted)

    selected = max((nodes[key] for key in current["next"]),
                   key=lambda node: (matches(node["type"]), sum(matches(nodes[key]["type"]) for key in node["next"])))
    page.locator(f'{VIEW} [data-node="{selected["id"]}"]').click()
    page.locator("dialog.hollow-map-entry").get_by_role("button",name="入場",exact=True).click()
    return selected


def resolve_scene(host, player, get_state, node, seen, photos, contrasts):
    view, guest = (page.locator(VIEW) for page in (host,player))
    floor = node["floor"]
    expect(view.locator(".he-screen")).to_be_visible(timeout=15000)
    expect(guest.get_by_text("ホストが選んでいます",exact=True)).to_be_visible()
    expect(guest.locator("[data-event-choice], [data-event-member], [data-event-action]")).to_have_count(0)
    event = get_state()["hollow"]["run"]["current_event"]
    if node["type"] == "miasma":
        step = next((key for key in ("成功","失敗","判定なし","通過") if key not in seen),"通過")
        choice = {"成功":0,"失敗":0,"判定なし":1,"通過":2}[step]
        view.locator(f"[data-event-choice='{choice}']").click()
        if choice < 2:
            name = "観測者" if step == "失敗" else "探索者"
            member = view.locator(".he-member").filter(has_text=name)
            member.click()
            if choice == 0:
                expect(member).to_contain_text("0%" if step == "失敗" else "100%")
                if "1280-魔素だまりホスト.png" not in photos:
                    shot(photos,host,"1280-魔素だまりホスト")
                    shot(photos,player,"1280-魔素だまりプレイヤー")
                    contrasts.extend(host.evaluate(CONTRAST,[[".he-choice b",None],[".he-choice small",None],
                                                            [".he-member strong",None],[".he-choice","borderTopColor"],
                                                            [".he-member","borderTopColor"],
                                                            [".he-panel h2",None],[".he-choice > span",None]]))
                    host.set_viewport_size({"width":700,"height":850})
                    shot(photos,host,"700-魔素だまり")
                    host.set_viewport_size({"width":1280,"height":860})
        view.locator("[data-event-action=decide]").click()
        expect(view.locator("[data-event-action=close]")).to_be_visible()
        if choice == 0:
            expect(view.locator(".he-dice strong")).to_have_text(step)
            shot(photos,host,"1280-結果" + step)
    else:
        kind = event["loot"]["kind"]
        step = kind if kind not in seen else "見送り"
        if step == kind:
            if kind == "item":
                view.locator(".he-member").filter(has_text="探索者").click()
            shot(photos,host,"1280-宝箱" + ("アイテム" if kind == "item" else "淵遺物"))
            if kind == "relic":
                contrasts.extend(host.evaluate(CONTRAST,[[".he-loot .hr-effect",None],
                                                         [".he-loot .hr-reward-card","borderTopColor"]]))
            else:
                expect(view.locator(".he-gain p")).not_to_be_empty()
            view.locator("[data-event-action=take]").click()
        else:
            view.locator("[data-event-action=skip]").click()
        expect(view.locator("[data-event-action=close]")).to_be_visible()
    seen.add(step)
    expect(guest.locator("[data-event-action=close]")).to_be_visible()
    close_result(host)
    expect(guest.locator("[data-event-action=close]")).to_be_visible()
    close_result(player)
    result = get_state()["hollow"]["run"]["current_event"]["result"]
    return f"{floor}F {step}: {result.get('total','—')} / {(result.get('gain') or {}).get('name','—')}"


def play_route(host, player, room, owned, photos, contrasts):
    code = api(host,"POST","/api/hollow/rooms",room_name=room)["join_code"]
    api(player,"POST","/api/join_room_by_code",room_name=room,join_code=code,play_mode="hollow")
    for page,key in zip((host,player),owned,strict=True):
        enter_room(page,room)
        command(page,"hollow_party_add_owned",owned_ids=[key])
    get_state = lambda: api(host,"GET","/load_room?" + urlencode({"name":room}))
    click(host,"ランを始める")
    host.locator(".hollow-choice-card").filter(has_text="青晶洞").click()
    click(host,"進む")
    expect(host.locator(f"{VIEW} [data-node]").first).to_be_visible()
    seen, lines = set(), []
    miasma = {"成功","失敗","判定なし","通過"}
    chest = {"item","relic","見送り"}
    for floor in range(1,11):
        run = get_state()["hollow"]["run"]
        wanted = ({"miasma"} if not miasma <= seen else set()) | ({"chest"} if not chest <= seen else set())
        node = choose_node(host,run,wanted)
        if node["type"] in ("battle","elite","boss"):
            expect(host.locator("#map-viewport")).to_be_visible()
            for _ in range(5):
                state = resolve_round(host,get_state,room)
                if state["combat_phase"] == "ready":
                    break
            run = state["hollow"]["run"]
            assert run["current_event"]["outcome"] == "VICTORY"
            lines.append(f"{floor}F {node['type']} 勝利")
            if run.get("reward"):
                click(host,"見送る")
        else:
            lines.append(resolve_scene(host,player,get_state,node,seen,photos,contrasts))
        if floor == 9:
            click(host,"変転を終えてボスへ")
        if floor == 10:
            expect(host.locator(".he-rest")).to_be_visible()
            expect(host.locator(".he-rest li")).to_have_count(2)
            shot(photos,host,"1280-町")
            close_result(host)
            close_result(player)
            expect(host.locator(".hollow-choice-card").filter(has_text="古い晶脈")).to_be_visible()
            lines.append("石灯の町 → T2 マップ候補")
    command(host,"hollow_retreat")
    return seen, lines


def verify(browser):
    suffix = uuid4().hex[:6]
    author = register(browser,"EventAuthor" + suffix,author=True)
    host,player = [register(browser,name + suffix) for name in ("EventHost","EventGuest")]
    errors,photos,contrasts = [],{},[]
    for page in (author,host,player):
        page.on("pageerror",lambda error: errors.append(error.stack or str(error)))
    edit_library(author,photos)
    owned = [make_owned(host,"探索者",14),make_owned(player,"観測者",0)]
    logs,covered = [],set()
    required = {"成功","失敗","判定なし","通過","item","relic","見送り"}
    for attempt in range(5):
        seen, lines = play_route(host,player,f"魔素探索 {suffix}-{attempt}",owned,photos,contrasts)
        covered.update(seen)
        logs.extend(lines)
        if required <= covered:
            break
    assert required <= covered, covered
    assert not errors, errors
    assert all(ratio >= minimum for _,ratio,minimum in contrasts), contrasts
    print("\n".join(logs))
    print("Contrast:", contrasts)
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python",default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python,exercise=verify)
    OUT.mkdir(parents=True,exist_ok=True)
    for name,photo in photos.items():
        (OUT / name).write_bytes(photo)
    print(f"Saved {len(photos)} screenshots to {OUT}")
