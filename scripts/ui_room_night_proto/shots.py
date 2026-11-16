"""Capture the actual room UI through a local app started with --db."""
import argparse
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ART = "/static/images/"
CAVE = ART + "backgrounds/暗い遺跡洞窟.png"
HEIGHT = 800
WIDTHS = (1280, 1024)


def actor(index, ally, owner, user_id):
    names = ["リュカ", "ミレイ", "セナ", "ロアン"] if ally else ["遺跡の番兵", "影の斥候"]
    portraits = ["男冒険者", "女冒険者"] if ally else ["人狼型シュラーカー", "小人型シュラーカー"]
    return {
        "id": f"{'pc' if ally else 'npc'}-{index}",
        "name": names[index],
        "type": "ally" if ally else "enemy",
        "owner": owner,
        "owner_id": user_id,
        "x": 2 + index % 2 if ally else 5,
        "y": 1 + 2 * (index // 2) if ally else 1 + 2 * index,
        "image": ART + f"characters/{portraits[index % 2]}.png",
        "hp": 31 - index * 4, "maxHp": 42,
        "mp": 15 + index, "maxMp": 24,
        "states": [{"name": "FP", "value": 8 + index * 3}],
        "commands": "2d6 【Ps-01 斬撃】\n2d6 【Ps-04 薙ぎ払い】",
        "params": [{"label": "速度", "value": 2}, {"label": "五感", "value": 3}],
        "inventory": {"I-01": 2, "I-02": 1},
        "special_buffs": [{"buff_id": "Bu-08", "name": "出血維持", "lasting": 2, "value": 2, "data": {}}] if ally else [],
        "flags": {},
        "tokenScale": .68,
    }


def post(page, route, body):
    response = page.request.post(route, data=body)
    assert response.ok, f"{route}: {response.status} {response.text()}"
    return response.json()


def emit(page, event, payload):
    return page.evaluate("""([event, payload]) => new Promise((resolve, reject) => {
        socket.timeout(5000).emit(event, {room: currentRoomName, ...payload},
            (error, ...values) => error ? reject(error) : resolve(values));
    })""", [event, payload])


def prepare_room(page, base, queue_only=False):
    tag = uuid4().hex[:8]
    room = f"遺跡の見張り台 · {tag}"
    player = "ミレイ"
    user = post(page, "/api/register", {"login_name": f"night{tag}", "password": uuid4().hex,
                                      "display_name": player})
    created = post(page, "/create_room", {"room_name": room, "gm_pin": "5219"})
    if not queue_only:
        pcs = [actor(i, True, player, user["user_id"]) for i in range(4)]
        enemies = [actor(i, False, player, user["user_id"]) | {"x": -1, "y": -1} for i in range(2)]
        actors = pcs + enemies
        state = created["state"] | {
            "characters": actors, "character_owners": {char["id"]: player for char in actors},
            "mode": "exploration", "battle_mode": "pvp",
            "battle_map_data": {"background_image": CAVE},
            "exploration": {"backgroundImage": CAVE, "tachie_locations": {
                char["id"]: {"x": 50 + i * 135, "y": 230 + i % 2 * 45, "scale": .72}
                for i, char in enumerate(pcs)
            }},
        }
        post(page, "/save_room", {"room_name": room, "state": state})
    page.goto(base + "/#sessions")
    page.wait_for_function("window.socket?.connected")
    page.evaluate("name => joinRoom(name, null, {role: 'GM', gmPin: ''})", room)
    expect(page.locator("#current-room-name")).to_contain_text(room)
    page.wait_for_function("typeof window.openRoomEncounterQueue === 'function' && !!document.querySelector('#action-dock')")
    return room


def screenshot(page, directory, name, width):
    page.mouse.move(0, 0)
    page.evaluate("document.fonts.ready")
    page.screenshot(path=directory / f"{name}-{width}.png", animations="disabled")


def capture_queue(page, directory):
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": HEIGHT})
        page.locator("#visual-room-preset-btn").click()
        dialog = page.locator(".rq-dialog")
        dialog.get_by_role("button", name="＋ 新規", exact=True).click()
        dialog.locator("input").first.fill("遺跡の番兵")
        screenshot(page, directory, "queue", width)
        dialog.get_by_role("button", name="閉じる").click()
        page.evaluate("""() => {
          const pilot = openEncounterPlacement({
            placement: {width: 20, height: 15}, removed_ids: [],
            new_tokens: [{side: 'enemy', name: '遺跡の番兵'}]
          }, {confirm() {}, cancel() { pilot.close(); }});
        }""")
        expect(page.locator(".rq-ghost")).to_be_visible()
        screenshot(page, directory, "placement", width)
        page.locator(".rq-placement").get_by_role("button", name="取り消し").click()



def set_theme(page, mode, *, tokens=False, gems=False):
    page.evaluate("""({mode, tokens, gems}) => {
        const night = mode === 'night';
        document.body.toggleAttribute('data-gem-marks', night && gems);
        if (night) document.body.dataset.theme = 'night';
        else delete document.body.dataset.theme;
        if (night && tokens) document.body.dataset.tokenPalette = 'night';
        else delete document.body.dataset.tokenPalette;
        for (const surface of document.querySelectorAll(
          '#visual-log-area, .book-modal-backdrop, .glossary-catalog-backdrop, .declare-skill-detail')) {
            if (night) surface.dataset.theme = 'paper';
            else delete surface.dataset.theme;
        }
        for (const notice of document.querySelectorAll('.room-notices')) notice.hidden = !night;
    }""", {"mode": mode, "tokens": tokens, "gems": gems})


def frame_board(page):
    page.evaluate("""() => {
        const viewport = document.querySelector('#map-viewport');
        visualScale = Math.min(1.18, viewport.clientWidth / (4 * GRID_SIZE));
        visualOffsetX = viewport.clientWidth / 2 - GRID_SIZE * 3.5 * visualScale;
        visualOffsetY = viewport.clientHeight / 2 - GRID_SIZE * 2.5 * visualScale;
        window.visualViewNeedsCenter = false;
        updateMapTransform();
    }""")


def capture_pair(page, directory, name, *, variant=None):
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": HEIGHT})
        if name in ("b-board", "b-declare"):
            frame_board(page)
        for mode in ("current", "night"):
            set_theme(page, mode)
            if name in ("a", "b-board", "b-declare", "b-resolve"):
                page.locator("#visual-log-area").evaluate("(el) => el.scrollTop = 0")
            screenshot(page, directory, f"{name}-{mode}", width)
        if variant:
            set_theme(page, "night", tokens=variant == "tokens", gems=variant == "gems")
            screenshot(page, directory, f"{name}-{variant}", width)
    set_theme(page, "current")


def begin_round(page):
    emit(page, "request_change_mode", {"mode": "battle"})
    expect(page.locator("#map-viewport")).to_be_visible()
    for i in range(2):
        emit(page, "request_move_character", {"character_id": f"npc-{i}", "x": 4, "y": 1 + 2 * i})
    expect(page.locator(".map-token.Enemy")).to_have_count(2)
    emit(page, "request_combat_enter", {})
    emit(page, "request_new_round", {})
    page.wait_for_function("window.BattleStore?.state?.timeline.length >= 6")
    page.wait_for_timeout(2300)  # ラウンド開始の演出が終わってから比較する。
    return page.evaluate("""() => {
        const state = BattleStore.state;
        return {battle_id: state.battle_id, slots: Object.values(state.slots)};
    }""")


def capture_battle(page, directory, room):
    battle = begin_round(page)
    capture_pair(page, directory, "b-board", variant="tokens")
    slots = battle["slots"]
    allies = [slot["slot_id"] for slot in slots if slot["team"] == "ally"]
    enemies = [slot["slot_id"] for slot in slots if slot["team"] == "enemy"]
    page.evaluate("""([sourceSlotId, targetSlotId]) => BattleStore.setDeclare({
        sourceSlotId, targetSlotId, skillId: 'Ps-01', mode: 'editing',
    })""", [allies[0], enemies[0]])
    expect(page.locator("#select-resolve-declare-panel-left")).to_be_visible()
    capture_pair(page, directory, "b-declare")
    page.evaluate("BattleStore.resetDeclare()")
    for src, target in [(slot, enemies[i % len(enemies)]) for i, slot in enumerate(allies)] + [
        (slot, allies[i % len(allies)]) for i, slot in enumerate(enemies)
    ]:
        emit(page, "battle_intent_commit", {
            "room_id": room, "battle_id": battle["battle_id"], "slot_id": src,
            "skill_id": "Ps-01", "target": {"type": "single_slot", "slot_id": target},
        })
    page.wait_for_function("Object.values(BattleStore.state.intents).filter(intent => intent.committed).length >= 6")
    emit(page, "battle_resolve_start", {"room_id": room, "battle_id": battle["battle_id"]})
    expect(page.locator(".resolve-flow-next-btn")).to_be_visible(timeout=20000)
    expect(page.locator(".resolve-flow-next-btn")).to_be_enabled(timeout=20000)
    capture_pair(page, directory, "b-resolve")
    for _ in range(len(slots) + 1):
        if page.evaluate("BattleStore.state.resolvePresentation?.status === 'completed'"):
            break
        next_button = page.locator(".resolve-flow-next-btn")
        expect(next_button).to_be_enabled(timeout=20000)
        next_button.click()
        page.wait_for_timeout(500)
    page.wait_for_function("BattleStore.state.resolvePresentation?.status === 'completed'")


def capture_windows(page, directory):
    page.evaluate("openCharacterModal('pc-0')")
    character = page.locator("#char-modal-backdrop")
    expect(character.get_by_text("特殊効果 / バフ")).to_be_visible()
    character.locator(".modal-content").evaluate(
        "(el) => el.scrollTop = Math.max(0, el.querySelector('.detail-buff-accordion-list').offsetTop - 290)"
    )
    capture_pair(page, directory, "c-character")
    page.evaluate("closeCharacterModal()")

    page.evaluate("openItemModal(); showItemList('pc-0')")
    items = page.locator("#item-modal-backdrop")
    expect(items.locator(".item-card").first).to_be_visible()
    capture_pair(page, directory, "c-items", variant="gems")
    items.locator(".close-btn").click()

    page.evaluate("openSkillDetailModal('Ps-01', '斬撃')")
    book = page.locator(".book-modal-backdrop")
    expect(book.locator(".book-reading-body")).to_be_visible()
    capture_pair(page, directory, "c-skill")
    book.locator(".book-modal-close").click()


def capture_notices(page, directory):
    page.evaluate("""() => {
        void showAppConfirm('待機列の変更を保存しますか？', {
            title: '遭遇を保存', confirmText: '保存', defaultFocus: 'cancel',
        });
    }""")
    expect(page.locator("#app-dialog-title")).to_have_text("遭遇を保存")
    capture_pair(page, directory, "d-confirm")
    page.locator("#app-dialog-cancel").click()
    page.evaluate("""() => {
        void showAppAlert('遭遇名が空です。名前を入力してから保存してください。', {title: '保存できません'});
    }""")
    expect(page.locator("#app-dialog-title")).to_have_text("保存できません")
    capture_pair(page, directory, "d-error")
    page.locator("#app-dialog-confirm").click()

    # Use the current room's status line as the reference. Keep both proposed notices
    # visible in the captures so their hierarchy can be judged side by side.
    page.evaluate("""() => {
        document.querySelector('#visual-status-msg').textContent = '保存しました。';
        const notices = document.createElement('section');
        notices.className = 'room-notices';
        notices.hidden = true;
        notices.innerHTML = '<div class="room-notice" role="alert"><strong>保存できません</strong>遭遇名を入力してください。 <button type="button" aria-label="閉じる">×</button></div>'
            + '<div class="room-notice" role="status"><strong>保存しました</strong>「遺跡の番兵」を待機列に追加しました。</div>';
        document.body.append(notices);
    }""")
    capture_pair(page, directory, "d-notices")


def capture_prototype(page, directory, room):
    page.add_style_tag(path=Path(__file__).with_name("night.css"))
    expect(page.locator(".exploration-tachie")).to_have_count(4)
    lines = [
        "入口に残った足跡は四つ。奥へ向かった三人分と、入口を見張るように横を向いた一人分がある。"
        "床の石に泥が残っているから、通ったのはついさっきだと思う。灯りを落として、右手の壁に沿って進もう。",
        "了解。私は最後尾に付いて退路を見ておく。水音が近づいたらいったん止まって、合図を待って。",
        "/roll 2d6+3",
    ]
    for line in lines:
        emit(page, "request_chat", {"message": line})
    expect(page.locator("#visual-log-area")).to_contain_text("2d6+3 →")
    capture_pair(page, directory, "a")
    capture_windows(page, directory)
    capture_battle(page, directory, room)
    capture_notices(page, directory)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--queue-only", type=Path, help="待機列と登場位置の比較用写真の出力先")
    args = parser.parse_args()
    output = args.queue_only or ROOT / "_local/ui_room_night_proto/shots"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        page = browser.new_page(base_url=args.base, viewport={"width": 1280, "height": HEIGHT})
        room = prepare_room(page, args.base, queue_only=bool(args.queue_only))
        if args.queue_only:
            capture_queue(page, output)
        else:
            capture_prototype(page, output, room)
        browser.close()


if __name__ == "__main__":
    main()
