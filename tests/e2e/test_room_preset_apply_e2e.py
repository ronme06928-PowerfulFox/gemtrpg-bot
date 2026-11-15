import os
from uuid import uuid4

import pytest


pytestmark = pytest.mark.e2e


def test_room_encounter_queue_e2e():
    if os.environ.get("RUN_ROOM_PRESET_E2E") != "1":
        pytest.skip("Set RUN_ROOM_PRESET_E2E=1 with an isolated app and seeded unit catalog.")

    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    base = os.environ.get("ROOM_PRESET_E2E_BASE_URL", "http://127.0.0.1:5000")
    token = uuid4().hex[:8]

    def post(page, url, **body):
        response = page.request.post(url, data=body)
        assert response.ok, response.text()
        return response.json()

    def login(page, label):
        post(page, "/api/register", login_name=f"Encounter{label}{token}", password=uuid4().hex)
        page.goto(base)
        page.wait_for_function("window.socket?.connected")

    def enter(page, room, role):
        page.evaluate("([name, role]) => joinRoom(name, null, {role, gmPin: ''})", [room, role])
        expect(page.locator("#current-room-name")).to_contain_text(room)

    def save_stage(page):
        page.locator("#visual-room-preset-btn").click()
        dialog = page.locator(".rq-dialog")
        dialog.get_by_role("button", name="＋ 新規", exact=True).click()
        dialog.locator(".rq-resource button").first.click()
        dialog.get_by_role("button", name="保存前チェック").click()
        dialog.get_by_role("button", name="保存確定").click()
        expect(dialog.locator(".rq-card")).to_have_count(1)
        return dialog

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        gm = browser.new_page(base_url=base, viewport={"width": 1280, "height": 800})
        pl = browser.new_page(base_url=base, viewport={"width": 680, "height": 800})
        login(gm, "GM")
        login(pl, "PL")
        room = f"Encounter-{token}"
        post(gm, "/create_room", room_name=room, gm_pin="5219")
        post(gm, "/api/room/update_settings", room_name=room, lobby_visibility="listed")
        post(pl, "/api/join_room_by_code", room_name=room)
        enter(gm, room, "GM")
        enter(pl, room, "Player")
        dialog = save_stage(gm)
        expect(pl.locator("#visual-room-preset-btn")).to_be_hidden()
        dialog.get_by_role("button", name="登場", exact=True).click()
        expect(gm.locator(".rq-board-input")).to_be_visible()
        expect(pl.locator(".rq-board-input")).to_have_count(0)
        gm.get_by_role("button", name="自動で置く").click()
        dialog.get_by_role("button", name="確定", exact=True).click()
        expect(gm.locator(".rq-placement")).to_contain_text("済")
        pl.wait_for_function("battleState.characters.length > 0")
        assert pl.evaluate("!('encounter_queue' in battleState)")

        battle_room = f"EncounterDraft-{token}"
        post(gm, "/create_room", room_name=battle_room, gm_pin="5219", play_mode="battle_only")
        gm.get_by_role("button", name="待機列に戻る").click()
        dialog.get_by_role("button", name="閉じる").click()
        enter(gm, battle_room, "GM")
        dialog = save_stage(gm)
        dialog.get_by_role("button", name="下書きへ反映").click()
        dialog.get_by_role("button", name="確定", exact=True).click()
        expect(dialog.get_by_text("下書きに反映しました")).to_be_visible()
        dialog.get_by_role("button", name="詳細調整").click()
        expect(gm.locator("#bo-draft-backdrop")).to_be_visible()
        browser.close()
