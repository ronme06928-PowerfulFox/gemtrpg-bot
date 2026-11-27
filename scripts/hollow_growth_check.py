"""Play two T1 expeditions in the app and capture the first-clear results."""

import argparse
import sys
from urllib.parse import urlencode
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, ROOT, api, click, launch_and_verify, register
from scripts.hollow_run_check import choose, choose_map, command, enter_room, finish_reward, resolve_round, socket_call, wait_for
from scripts.hollow_seed import PREFIX

OUT = ROOT / "_local/pr35_17_shots"


def screenshot(page):
    return page.screenshot(animations="disabled")


def create_owned(page, name, skill):
    data = {"name":name,"commands":skill,
            "status":[{"label":key,"value":value,"max":value}
                      for key,value in (("HP",180),("MP",50),("FP",50))],
            "params":[{"label":"経験","value":1},{"label":"物理補正","value":200}]}
    return api(page,"POST","/api/owned_characters",data=data)["character"]["id"]


def saved_progress(page):
    return {row["id"]: (row["exp_total"],row["radiance_limit"],row["cleared_hollow_tiers"])
            for row in api(page,"GET","/api/owned_characters")["characters"]}


def play_tier_one(host, player, room, party, expected_names, photos=None):
    code = api(host,"POST","/api/hollow/rooms",room_name=room)["join_code"]
    api(player,"POST","/api/join_room_by_code",room_name=room,join_code=code,play_mode="hollow")
    for page, ids in zip((host,player),party,strict=True):
        enter_room(page,room)

        def add_to_party():
            reply = socket_call(page,"hollow_party_add_owned",{"owned_ids":ids})
            assert reply["ok"] or reply["error"] == "部屋に入室してください", reply
            return reply

        wait_for(add_to_party,lambda reply: reply["ok"])
    command(host,"hollow_run_start")

    def state():
        return api(host,"GET","/load_room?" + urlencode({"name":room}))

    choose_map(host,state,1,2,name=f"{PREFIX} 青晶洞")
    for floor in range(1,11):
        choose(host,state(),floor)
        for _ in range(5):
            end = resolve_round(host,state,room)
            if end["combat_phase"] == "ready":
                break
        run = end["hollow"]["run"]
        assert run["current_event"]["outcome"] == "VICTORY", run["current_event"]
        finish_reward(host,run)
        if floor == 9:
            command(host,"hollow_end_fusion",floor=9)
    message = f"T1 初踏破：{'・'.join(expected_names)}（経験＋1・通過点＋1）"
    for page in (host,player):
        expect(page.locator("#visual-log-area").get_by_text(message,exact=False)).to_be_visible()
    if photos is not None:
        host.locator("#visual-log-area").get_by_text(message,exact=False).scroll_into_view_if_needed()
        photos["1280-初踏破ログ.png"] = screenshot(host)
    command(host,"hollow_retreat")
    for page in (host,player):
        results = page.locator(".hollow-growth-results li")
        expect(results).to_have_count(len(expected_names))
        for name in expected_names:
            expect(results.filter(has_text=name)).to_contain_text("経験＋1・通過点＋1")
    assert state()["hollow"]["run"]["result"]["outcome"] == "RETREAT"
    if photos is not None:
        photos["1280-ランの結果.png"] = screenshot(host)
    return message


def verify(browser):
    suffix = uuid4().hex[:6]
    host,player = (register(browser,label+suffix) for label in ("GrowthHost","GrowthPlayer"))
    author = register(browser,"GrowthAuthor"+suffix,author=True)
    photos, errors = {}, []
    for page in (host,player,author):
        page.emulate_media(reduced_motion="reduce")
        page.on("pageerror",lambda error: errors.append(error.stack or str(error)))

    skill = api(host,"GET","/api/get_skill_data")["Ps-01"]["チャットパレット"]
    names = [("リオ","カイ"),("ミナ","ナギ")]
    party = [[create_owned(page,name,skill) for name in pair]
             for page,pair in zip((host,player),names,strict=True)]
    assert all(value == (1,0,[]) for page in (host,player) for value in saved_progress(page).values())
    first = play_tier_one(host,player,"初踏破 " + suffix,party,["リオ","カイ","ミナ","ナギ"],photos)
    for page, ids in zip((host,player),party,strict=True):
        assert all(saved_progress(page)[key] == (2,1,[1]) for key in ids)
        click(page,"ダンジョンへ戻る")
        click(page,"戻る")
        page.wait_for_url("**/#dungeon")
        page.goto(BASE + "/#characters")
        expect(page.locator(".owned-chars-hollow-clear")).to_have_count(2)
        expect(page.locator(".owned-chars-exp").first).to_have_text("1")
        expect(page.locator(".owned-chars-pass").first).to_have_text("1")
    photos["1280-持ちキャラ一覧.png"] = screenshot(host)

    newcomer = create_owned(player,"スイ",skill)
    second = play_tier_one(host,player,"再踏破 " + suffix,[party[0],[party[1][0],newcomer]],["スイ"])
    assert all(value == (2,1,[1]) for page in (host,player) for value in saved_progress(page).values())

    tier = next(row for row in api(author,"GET","/api/units/tier?domain=hollow")["entries"]
                if row["payload"]["tier"] == 1)
    author.goto(BASE + "/#hollow-data")
    expect(author.get_by_role("button",name="＋ 新規",exact=True)).to_be_visible()
    author.locator('.unit-tabs [data-kind="tier"]').click()
    author.locator(f'.unit-records [data-id="{tier["entry_id"]}"]').click()
    for name in ("boss_exp","boss_radiance"):
        expect(author.locator(f'.unit-section [data-path="{name}"]')).to_have_value("1")
    photos["1280-Tier設定.png"] = screenshot(author)
    assert not errors, errors
    print(first)
    print(second)
    print("持ちキャラ5体とも獲得経験1・獲得通過点1（蓄積経験2）、踏破Tierは[1]")
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python",default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python,exercise=verify)
    OUT.mkdir(parents=True,exist_ok=True)
    for name, photo in photos.items():
        (OUT / name).write_bytes(photo)
    print(f"Saved {len(photos)} screenshots to {OUT}")
