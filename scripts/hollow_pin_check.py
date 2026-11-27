"""Verify PR35-18 recommendation pins with a host and two players on a disposable seeded DB.

Usage:
    python scripts/hollow_seed.py --db _local/agent_db/gemtrpg.db
    python -m scripts.hollow_pin_check
"""

import argparse
import sys
from urllib.parse import urlencode
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, CONTRAST, ROOT, api, click, launch_and_verify, register
from scripts.hollow_event_ui_check import choose_node, close_result, make_owned, shot
from scripts.hollow_run_check import command, enter_room, resolve_round, wait_for

VIEW = "#hollow-map-view"
OUT = ROOT / "_local/pr35_18_shots"


def by_user(get_state):
    return get_state()["hollow"]["run"]["pins"]["by_user"]


def wait_pins(get_state, count):
    return wait_for(get_state, lambda state: len(state["hollow"]["run"]["pins"]["by_user"]) == count)


def pin(page, selector):
    page.locator(f"{VIEW} {selector}").first.click()


def check_cleared(get_state, scene):
    state = wait_for(get_state, lambda value: value["hollow"]["run"]["pins"]["scene"] != scene)
    assert state["hollow"]["run"]["pins"]["by_user"] == {}, state["hollow"]["run"]["pins"]


def verify(browser):
    suffix = uuid4().hex[:6]
    host, first, second = [register(browser, name + suffix) for name in ("PinHost", "PinA", "PinB")]
    pages = (host, first, second)
    errors, photos, contrasts, lines = [], {}, [], []
    for page in pages:
        page.on("pageerror", lambda error: errors.append(error.stack or str(error)))
    owned = [make_owned(page, name, 3) for page, name in zip(pages, ("先導", "斥候", "後衛"), strict=True)]
    room = f"ピン {suffix}"
    code = api(host, "POST", "/api/hollow/rooms", room_name=room)["join_code"]
    for page in (first, second):
        api(page, "POST", "/api/join_room_by_code", room_name=room, join_code=code, play_mode="hollow")
    for page, key in zip(pages, owned, strict=True):
        enter_room(page, room)
        command(page, "hollow_party_add_owned", owned_ids=[key])
    get_state = lambda: api(host, "GET", "/load_room?" + urlencode({"name": room}))
    click(host, "ランを始める")

    # マップを選ぶ：2人が同じ札にピン
    expect(first.locator(f"{VIEW} .hollow-choice-card[data-pin]").first).to_be_visible()
    pin(first, ".hollow-choice-card[data-pin]")
    pin(second, ".hollow-choice-card[data-pin]")
    wait_pins(get_state, 2)
    expect(host.locator(f"{VIEW} .hollow-choice-card").first.locator(".hollow-pins i")).to_have_count(2)
    expect(first.locator(f"{VIEW} .hollow-pin-hint")).to_contain_text("ピン 2 / 2人")
    expect(host.locator(f"{VIEW} .hollow-pin-hint")).to_have_text("ピン 2 / 2人")
    shot(photos, first, "1280-マップを選ぶ")
    host.locator(f"{VIEW} .hollow-choice-card").filter(has_text="青晶洞").click()
    click(host, "進む")
    check_cleared(get_state, "maps:1")
    lines.append("マップを選ぶ：2本 → 決定で消えた")

    # 次のマス：1人はマス、1人は撤退。外す・移す
    expect(first.locator(f"{VIEW} .hollow-node[data-pin]").first).to_be_visible()
    pin(first, ".hollow-node[data-pin]")
    pin(second, '.hollow-map-head [data-pin="retreat"]')
    wait_pins(get_state, 2)
    scene = get_state()["hollow"]["run"]["pins"]["scene"]
    expect(host.locator(f"{VIEW} .hollow-node .hollow-pins i")).to_have_count(1)
    expect(host.locator(f"{VIEW} .hollow-map-head .hollow-pins i")).to_have_count(1)
    expect(first.locator(f"{VIEW} .hollow-node[data-pin][aria-pressed=true]")).to_have_count(1)
    shot(photos, host, "1280-次のマス・ホスト")
    shot(photos, first, "1280-次のマス・プレイヤー")
    contrasts.extend(first.evaluate(CONTRAST, [[".hollow-pins i", None], [".hollow-pins i", "backgroundColor"],
                                               [".hollow-pin-hint", None]]))
    first.set_viewport_size({"width": 700, "height": 860})
    shot(photos, first, "700-次のマス")
    first.set_viewport_size({"width": 1280, "height": 860})
    pin(first, ".hollow-node[data-pin][aria-pressed=true]")
    wait_pins(get_state, 1)
    pin(first, '.hollow-map-head [data-pin="retreat"]')
    wait_pins(get_state, 2)
    assert set(by_user(get_state).values()) == {"retreat"}
    lines.append("次のマス：立てる・外す・撤退へ移す")

    seen = set()
    for floor in range(1, 10):
        run = get_state()["hollow"]["run"]
        wanted = {kind for kind in ("miasma", "chest") if kind not in seen}
        node = choose_node(host, run, wanted)
        check_cleared(get_state, scene)
        if node["type"] in ("battle", "elite", "boss"):
            for _ in range(5):
                state = resolve_round(host, get_state, room)
                if state["combat_phase"] == "ready":
                    break
            if state["hollow"]["run"].get("reward"):
                expect(first.locator(f"{VIEW} .hr-reward-card[data-pin]").first).to_be_visible()
                pin(first, ".hr-reward-card[data-pin]")
                pin(second, '[data-pin="skip"]')
                wait_pins(get_state, 2)
                if "reward" not in seen:
                    expect(host.locator(f"{VIEW} .hr-reward-card .hollow-pins i")).to_have_count(1)
                    shot(photos, host, "1280-報酬")
                    seen.add("reward")
                reward_scene = get_state()["hollow"]["run"]["pins"]["scene"]
                host.locator(f'{VIEW} [data-relic-action="skip"]').click()
                check_cleared(get_state, reward_scene)
                lines.append(f"{floor}F 報酬：2本 → 見送りで消えた")
        else:
            event_scene = f"{node['type']}:{floor}"
            if node["type"] == "miasma":
                pin(first, ".he-choice[data-pin]")
                wait_pins(get_state, 1)
                if "miasma" not in seen:
                    expect(host.locator(f"{VIEW} .he-choice .hollow-pins i")).to_have_count(1)
                    shot(photos, first, "1280-魔素だまり")
                choices = get_state()["hollow"]["run"]["current_event"]["choices"]
                member = get_state()["hollow"]["run"]["party_order"][0]
                command(host, "hollow_resolve_miasma", floor=floor, choice_index=len(choices) - 1, char_id=member)
            else:
                pin(first, '[data-pin="take"]')
                pin(second, '[data-pin="skip"]')
                wait_pins(get_state, 2)
                if "chest" not in seen:
                    shot(photos, second, "1280-宝箱")
                command(host, "hollow_resolve_chest", floor=floor, take=False)
            check_cleared(get_state, event_scene)
            for page in pages:
                close_result(page)
            seen.add(node["type"])
            lines.append(f"{floor}F {node['type']}：ピン → 決定で消えた")
        if floor == 9 or {"reward", "miasma", "chest"} <= seen:
            break
        scene = get_state()["hollow"]["run"]["pins"]["scene"]
    else:
        raise AssertionError("route ended")
    if get_state()["hollow"]["run"].get("fusion"):
        click(host, "変転を終えてボスへ")
    scene = get_state()["hollow"]["run"]["pins"]["scene"]
    assert scene and scene.startswith("node:"), scene

    # 退出した人のピンは消える
    pin(second, '.hollow-map-head [data-pin="retreat"]')
    pin(first, '.hollow-map-head [data-pin="retreat"]')
    wait_pins(get_state, 2)
    leaving = next(member["id"] for member in get_state()["hollow"]["members"] if member["name"] == "PinB" + suffix)
    api(host, "POST", "/api/room/remove_member", room_name=room, user_id=leaving)
    wait_for(get_state, lambda state: leaving not in state["hollow"]["run"]["pins"]["by_user"])
    assert len(by_user(get_state)) == 1
    lines.append("退出：その人のピンだけ消えた")
    command(host, "hollow_retreat")

    assert not errors, errors
    assert all(ratio >= minimum for _, ratio, minimum in contrasts), contrasts
    print("\n".join(lines))
    print("Seen:", sorted(seen))
    print("Contrast:", contrasts)
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python, exercise=verify)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, photo in photos.items():
        (OUT / name).write_bytes(photo)
    print(f"Saved {len(photos)} screenshots to {OUT}")
