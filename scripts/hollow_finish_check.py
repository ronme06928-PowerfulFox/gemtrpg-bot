"""Exercise PR35-19, including two 50F clears on a disposable seeded DB."""

import argparse
from contextlib import closing
import json
import sqlite3
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep
from urllib.parse import urlencode
from uuid import uuid4

from playwright.sync_api import expect

from manager.hollow.map import build_map
from scripts.hollow_data_proto import check_app
from scripts.hollow_data_proto.check_app import BASE, CONTRAST, DB, DB_DIR, ROOT, api, click, launch_and_verify, register
from scripts.hollow_run_check import choose_map, command, create_owned, enter_room, finish_reward, resolve_round, wait_for

OUT = ROOT / "_local/pr35_19_shots"
FOG = ".hollow-fog-canvas"


def room_state(page, title):
    return api(page,"GET","/load_room?" + urlencode({"name":title}))


def room_disk_state(title):
    with closing(sqlite3.connect(DB.as_uri() + "?mode=ro",uri=True)) as conn:
        row = conn.execute("SELECT data FROM rooms WHERE name = ?",(title,)).fetchone()
        return json.loads(row[0]) if row else {}


def shot(photos, page, filename):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    name = filename + ".png"
    photos[name] = page.screenshot(animations="allow")
    (OUT / name).write_bytes(photos[name])


def stage_room(host, player, title, owned):
    code = api(host,"POST","/api/hollow/rooms",room_name=title)["join_code"]
    api(player,"POST","/api/join_room_by_code",room_name=title,join_code=code,play_mode="hollow")
    for page, key in zip((host,player),owned,strict=True):
        enter_room(page,title)
        expect(page.locator("#hollow-map-view h2")).to_have_text("出発前")
        command(page,"hollow_party_add_owned",owned_ids=[key])


def enter_node(host):
    host.locator(".hollow-node.is-next").first.click()
    dialog = host.locator("dialog.hollow-map-entry")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button",name="入場",exact=True).click()


def battle(host, title):
    state = lambda: room_state(host,title)
    for _ in range(5):
        wait_for(state, lambda current: current.get('battle_state', {}).get('phase') == 'select'
                 and current['battle_state'].get('slots'))
        ended = resolve_round(host,state,title)
        if ended["combat_phase"] == "ready":
            run = ended["hollow"]["run"]
            assert run["current_event"]["outcome"] == "VICTORY",run["current_event"]
            return run
    raise AssertionError("戦闘が終わりません")


def canvas_pixels(canvas):
    return canvas.evaluate("el => el.toDataURL()")


def check_fog(host, player, title, photos, contrasts):
    expect(host.locator(".hollow-depth-top")).to_contain_text("出発前")
    shot(photos,host,"1280-深度計-出発前")
    command(host,"hollow_run_start")
    area = choose_map(host,lambda: room_state(host,title),1,2)
    for page in (host,player):
        expect(page.locator(".hollow-depth-name")).to_have_text("T1 " + area["name"])
        expect(page.locator(FOG)).to_be_visible()
        assert page.locator(".hollow-map-row.is-fog [data-node]").count() == 0
    scroller = host.locator(".hollow-map-scroll")
    assert scroller.evaluate("el => {el.scrollTop=el.scrollHeight;return el.scrollTop>0;}")
    shot(photos,host,"1280-霧の地図")
    contrasts.extend(host.evaluate(CONTRAST,[[".is-fog .hollow-map-floor",None],[".hollow-map-fog",None]]))
    scroller.evaluate("el => {el.scrollTop=0;}")
    node = host.locator(".hollow-node.is-next").first
    node.hover()
    expect(host.locator(".hollow-map-tip")).to_be_visible()
    node.click()
    click(host,"キャンセル")
    for floor in (1,2):
        enter_node(host)
        expect(host.locator(FOG)).to_have_count(0)
        result = battle(host,title)
        finish_reward(host,result)
        expected = host.locator(f'.hollow-map-row.is-revealing[data-floor="{floor+2}"]')
        expect(expected).to_be_visible()
        if floor == 1:
            host.wait_for_timeout(450)
            shot(photos,host,"1280-霧が晴れる途中")
        expect(host.locator(".hollow-depth-top strong")).to_have_text(f"{floor}F")
        expect(expected).to_have_count(0)
    shot(photos,host,"1280-深度計-ラン中")
    contrasts.extend(host.evaluate(CONTRAST,[[".hollow-depth-top strong",None],[".hollow-depth-name",None],
                                               [".hollow-depth-sub b",None],[".hollow-depth-tier small",None],
                                               [".hollow-depth-tier i","backgroundColor"]]))
    player.reload()
    expect(player.locator(FOG)).to_be_visible()
    expect(player.locator(".is-revealing")).to_have_count(0)
    still_page = player.context.browser.new_page(base_url=BASE,storage_state=player.context.storage_state(),
        viewport={"width":700,"height":860},reduced_motion="reduce")
    enter_room(still_page,title)
    fog = still_page.locator(FOG)
    expect(fog).to_have_attribute("data-still","true")
    still_page.locator(".hollow-map-scroll").evaluate("el => {el.scrollTop=el.scrollHeight;}")
    still_page.wait_for_timeout(200)
    still = canvas_pixels(fog)
    still_page.wait_for_timeout(200)
    assert canvas_pixels(fog) == still
    shot(photos,still_page,"700-静止した霧と深度計")
    still_page.close()
    command(host,"hollow_retreat")


def setup(browser, photos, contrasts, snapshot_db):
    suffix = uuid4().hex[:6]
    host,player = (register(browser,name+suffix) for name in ("FinishHost","FinishPlayer"))
    author = register(browser,"FinishAuthor"+suffix,author=True)
    for page in (host,player,author):
        page.emulate_media(reduced_motion="no-preference")
    skill = api(host,"GET","/api/get_skill_data")["Ps-01"]["チャットパレット"]
    owned = [create_owned(page,name,skill,hp=200,strength=250)
             for page,name in zip((host,player),("リオ","ミナ"),strict=True)]
    title = "霧の確認 " + suffix
    stage_room(host,player,title,owned)
    check_fog(host,player,title,photos,contrasts)

    source = api(author,"GET","/api/units/hollow_map?domain=hollow")["entries"][0]["payload"]
    tiers = api(author,"GET","/api/units/tier?domain=hollow")["entries"]
    if not any(entry["payload"]["tier"] == 5 for entry in tiers):
        api(author,"POST","/api/units/tier",payload={"name":"深層境界","tier":5})
    area = api(author,"POST","/api/units/hollow_map",payload={**source,"name":"淵の喉","tier":5})["entry"]
    titles = ["通常演出の確認 " + suffix,"静止演出の確認 " + suffix]
    for title in titles:
        for page in (host,player):
            page.evaluate("window.forgetReconnectRoom()")
            page.goto("about:blank")
        stage_room(host,player,title,owned)
        command(host,"hollow_run_start")
        wait_for(lambda: room_disk_state(title).get("hollow",{}).get("run",{}),
                 lambda run: run.get("status") == "in_progress")
    # Copy the committed snapshot through SQLite while the app still owns its WAL.
    with closing(sqlite3.connect(DB.as_uri() + "?mode=ro",uri=True)) as source:
        with closing(sqlite3.connect(snapshot_db)) as copy:
            source.backup(copy)
            copy.execute("PRAGMA journal_mode=DELETE")
    return [page.context.storage_state() for page in (host,player)],titles,area


def position_at_49(titles, area, snapshot_db):
    # The app is stopped. Modify only the two named verification rooms.
    with closing(sqlite3.connect(snapshot_db)) as conn, conn:
        for title in titles:
            row = conn.execute("SELECT data FROM rooms WHERE name=?",(title,)).fetchone()
            state = json.loads(row[0])
            run = state["hollow"]["run"]
            assert state["play_mode"] == "hollow" and run["floor"] == 0
            layout = build_map({"tier":5,"name":"深層境界"},area["payload"],{},run["seed"])
            layout.update(map_id=area["entry_id"],map_name=area["payload"]["name"])
            layout["current"] = layout["rows"][-2][0]["id"]
            layout["visited"].append(layout["current"])
            run.update(floor=49,map=layout,mana_load=18)
            run.pop("map_candidates")
            run["log"] = [{"floor":floor,"type":"boss","outcome":"VICTORY"} for floor in (10,20,30,40)]
            conn.execute("UPDATE rooms SET data=? WHERE name=?",(json.dumps(state,ensure_ascii=False),title))


def final_boss(browser, credentials, title, photos, contrasts, *, reduced):
    host,player = [browser.new_page(base_url=BASE,storage_state=state,viewport={"width":1280,"height":860},
        reduced_motion="reduce" if reduced and index == 0 else "no-preference")
        for index,state in enumerate(credentials)]
    errors = []
    for page in (host,player):
        page.on("pageerror",lambda error: errors.append(error.stack or str(error)))
        enter_room(page,title)
        expect(page.locator(".hollow-depth-name")).to_have_text("T5 淵の喉")
        expect(page.locator(".hollow-depth-tier.is-cleared")).to_have_count(4)
    if reduced:
        player.evaluate("Fx.setLevel('light')")
    else:
        contrasts.extend(host.evaluate(CONTRAST,[[".hollow-depth-tier.is-cleared i","backgroundColor"]]))
    enter_node(host)
    run = battle(host,title)
    finish_reward(host,run)
    for page in (host,player):
        expect(page.locator("#hollow-map-curtain")).to_contain_text("制圧")
        expect(page.locator(".hollow-seal")).to_be_visible()
    if reduced:
        for page in (host,player):
            expect(page.locator(".hollow-seal.is-still")).to_be_visible()
        canvas = host.locator(".hd-shaft")
        host.wait_for_timeout(250)
        still = canvas_pixels(canvas)
        host.wait_for_timeout(250)
        assert canvas_pixels(canvas) == still
        shot(photos,host,"1280-封鎖-静止")
        click(host,"演出をスキップ")
        expect(host.locator(".hollow-seal")).to_have_count(0)
    else:
        host.wait_for_timeout(3750)
        shot(photos,host,"1280-封鎖-岩")
        for page in (host,player):
            expect(page.locator(".hollow-seal.is-title .hd-title")).to_be_visible()
        contrasts.extend(host.evaluate(CONTRAST,[[".hd-title",None]]))
        expect(host.locator(".hd-title")).to_have_css("opacity","1")
        shot(photos,host,"1280-封鎖-浅層踏破")
        for page in (host,player):
            expect(page.locator(".hollow-seal.is-verdict")).to_be_visible()
        contrasts.extend(host.evaluate(CONTRAST,[[".hd-verdict span:first-child",None],
                                                  [".hd-verdict span:last-child",None]]))
        expect(host.locator(".hd-verdict span").last).to_have_css("opacity","1")
        shot(photos,host,"1280-封鎖-二行の言葉")
    for page in (host,player):
        expect(page.locator(".hollow-seal")).to_have_count(0)
        expect(page.locator(".hollow-clear-lead")).to_have_text("浅層 50F 踏破")
        expect(page.locator(".hollow-depth-top")).to_contain_text("到達階 50F")
    if not reduced:
        shot(photos,host,"1280-クリアの結果")
    assert not errors, errors


def main(app_python):
    assert DB.is_relative_to(DB_DIR) and DB.is_file(), "Use a disposable seeded DB"
    OUT.mkdir(parents=True,exist_ok=True)
    photos,contrasts = {},[]
    with NamedTemporaryFile(dir=DB_DIR,prefix="pr35_19_boss_",suffix=".db",delete=False) as temp:
        snapshot_db = Path(temp.name)
    try:
        credentials,titles,area = launch_and_verify(app_python,
            exercise=lambda browser: setup(browser,photos,contrasts,snapshot_db))
        position_at_49(titles,area,snapshot_db)

        def verify(browser):
            for reduced,title in zip((False,True),titles,strict=True):
                final_boss(browser,credentials,title,photos,contrasts,reduced=reduced)

        check_app.DB = snapshot_db
        launch_and_verify(app_python,exercise=verify)
    finally:
        check_app.DB = DB
        for suffix in ("","-wal","-shm","-journal"):
            file = snapshot_db.with_name(snapshot_db.name + suffix)
            for attempt in range(10):
                try:
                    file.unlink(missing_ok=True)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    sleep(.2)
    assert all(value >= limit for _,value,limit in contrasts), contrasts
    print("Contrast:",contrasts)
    print(f"Fog, depth, two 50F clears and skip verified. Saved {len(photos)} screenshots to {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python",default=sys.executable)
    main(parser.parse_args().app_python)
