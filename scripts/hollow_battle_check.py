"""Play one round with two browser sessions on the disposable app database."""

import argparse
import sys
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, ROOT, api, click, launch_and_verify, register


def verify(browser):
    tag = uuid4().hex[:6]
    host, player = [register(browser, name + tag) for name in ("Rio", "Nagi")]
    errors, photos = [], {}
    room_name = "青晶坑・戦闘確認 " + tag
    code = api(host, "POST", "/api/hollow/rooms", room_name=room_name)["join_code"]
    api(player, "POST", "/api/join_room_by_code", room_name=room_name, join_code=code, play_mode="hollow")
    host_id = api(host, "GET", "/api/get_session_user")["user_id"]
    player_id = api(player, "GET", "/api/get_session_user")["user_id"]
    skill = api(host, "GET", "/api/get_skill_data")["Ps-01"]["チャットパレット"]
    characters = []
    for index, (key, name, team, owner, portrait) in enumerate([
        ("host", "岩牙", "ally", host_id, "男冒険者"),
        ("player", "晶殻", "ally", player_id, "女冒険者"),
        ("proxy", "夜風", "ally", player_id, "男冒険者"),
        ("enemy", "淵の番兵", "enemy", None, "人狼型シュラーカー"),
    ]):
        characters.append({
            "id": key, "name": name, "type": team, "owner_id": owner,
            "owner": {host_id: "Rio" + tag, player_id: "Nagi" + tag}.get(owner),
            "x": 10 if team == "ally" else 14, "y": 8 + index,
            "hp": 80, "maxHp": 80, "mp": 20, "maxMp": 20,
            "states": [{"name": "FP", "value": 8}],
            "params": [{"label": key, "value": 3} for key in ("速度", "五感", "物理補正")],
            "commands": skill, "image": f"/static/images/characters/{portrait}.png",
        })
    timeline = [{"id": row["id"] + "-1", "char_id": row["id"], "speed": 8 - i}
                for i, row in enumerate(characters)]
    api(host, "POST", "/save_room", room_name=room_name, state={
        "mode": "battle", "battle_mode": "pvp", "combat_phase": "active",
        "characters": characters, "timeline": timeline, "round": 1, "is_round_ended": False, "logs": [],
    })

    for page in (host, player):
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/#dungeon")
        page.locator(".dungeon-room").filter(has_text=room_name).get_by_role("button", name="入る").click()
        page.wait_for_function("window.BattleStore?.state?.round === 1 && window.currentUserId")
        expect(page.locator(".map-token")).to_have_count(4)
        for selector in ("#visual-round-start-btn", "#visual-round-end-btn", "#visual-room-preset-btn",
                         ".combat-session-action--enter", ".combat-session-action--conclude"):
            expect(page.locator(selector)).to_be_hidden()

    expect(host.locator("#visual-reset-btn")).to_be_visible()
    expect(player.locator("#visual-reset-btn")).to_be_hidden()
    expect(player.locator("#sr-resolve-confirm-btn")).to_have_count(0)
    player.evaluate("window.showCharacterDetail('host')")
    player.locator("#modal-settings-trigger").click()
    size_control = player.locator("#ctx-scale-slider")
    expect(size_control).to_be_disabled()
    host.evaluate("(id) => socket.emit('hollow_transfer_host', {user_id:id})", player_id)
    expect(player.locator("#visual-reset-btn")).to_be_visible()
    expect(player.locator("#sr-resolve-confirm-btn")).to_be_visible()
    expect(size_control).to_be_enabled()
    player.evaluate("(id) => socket.emit('hollow_transfer_host', {user_id:id})", host_id)
    expect(player.locator("#visual-reset-btn")).to_be_hidden()
    expect(player.locator("#sr-resolve-confirm-btn")).to_have_count(0)
    expect(size_control).to_be_disabled()
    player.locator("#char-modal-backdrop .modal-close-btn").click()

    def select_actor(page, source, target):
        page.evaluate("""([source, target]) => {
          const slots = Object.values(BattleStore.state.slots);
          const find = id => slots.find(slot => slot.actor_id === id && !slot.target_only).slot_id;
          BattleStore.setDeclare({sourceSlotId: find(source), targetSlotId: find(target),
            targetType: 'single_slot', skillId: null, mode: 'editing'});
        }""", [source, target])

    def declare(page, source, target, photo=None):
        select_actor(page, source, target)
        page.locator('.skill-picker-card[data-skill-id="Ps-01"]').click()
        commit = page.locator("#declare-commit-btn-header")
        expect(commit).to_be_enabled()
        if photo:
            photos[photo] = page.screenshot(animations="disabled")
        commit.click()
        page.wait_for_function(
            "id => Object.values(BattleStore.state.slots).some(s => s.actor_id === id && BattleStore.state.intents[s.slot_id]?.committed)",
            arg=source,
        )
        page.evaluate("BattleStore.resetDeclare()")

    select_actor(player, "host", "enemy")
    expect(player.locator("#declare-commit-btn-header")).to_be_hidden()
    declare(player, "player", "enemy", "1280-player-declare.png")
    declare(host, "proxy", "enemy", "1280-host-proxy.png")
    declare(host, "host", "enemy")
    declare(host, "enemy", "player")
    expect(host.locator("#sr-resolve-confirm-btn")).to_be_enabled()
    click(host, "解決開始")
    next_button = host.locator(".resolve-flow-next-btn")
    expect(next_button).to_be_visible(timeout=25000)
    expect(next_button).to_be_enabled(timeout=25000)
    expect(player.locator("#resolve-flow-panel")).to_be_visible()
    expect(player.locator(".resolve-flow-next-btn")).to_be_disabled()
    photos["1280-host-resolve.png"] = host.screenshot(animations="disabled")
    photos["1280-player-resolve.png"] = player.screenshot(animations="disabled")
    for _ in range(12):
        if host.evaluate("BattleStore.state.round > 1"):
            break
        if next_button.is_visible() and next_button.is_enabled():
            next_button.click()
        host.wait_for_timeout(900)
    for page in (host, player):
        page.wait_for_function("BattleStore.state.round === 2 && BattleStore.state.phase === 'select'", timeout=25000)
        expect(page.locator("#visual-round-start-btn")).to_be_hidden()
    photos["1280-next-round.png"] = player.screenshot(animations="disabled")
    assert not errors, errors
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python, exercise=verify)
    output = ROOT / "_local/pr35_7_shots"
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("1280-*.png"):
        if old.name not in photos:
            old.unlink()
    for name, data in photos.items():
        (output / name).write_bytes(data)
    print(f"Saved {len(photos)} screenshots in {output}")
