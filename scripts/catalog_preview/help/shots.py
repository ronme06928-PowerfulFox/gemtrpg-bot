"""管理画面の使い方ページの写真を、本物のアプリから撮る（計画60 §5.20 の試作）。

使い方：
  1. 手元の instance/gemtrpg.db ではない、別のフォルダからアプリを起動する（起動したときのカレントの instance/ が使われる）。
  2. python scripts/catalog_preview/help/shots.py --base http://127.0.0.1:5000 --db <そのフォルダ>/instance/gemtrpg.db
写真は _local/catalog_preview/help/shots/ に、1280×720 で書く。利用者は制作者とアプリ管理者の両方の印を付けて作る。
"""
import argparse
import sqlite3
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "_local" / "catalog_preview" / "help" / "shots"


def wait(page, ms=900):
    page.wait_for_timeout(ms)


def open_workspace(page, base):
    page.goto(base + "/")
    wait(page, 1500)
    page.get_by_role("button", name="マスターデータ", exact=True).first.click()
    wait(page, 1500)


def pick(page, text):
    page.locator(".bo-workspace__record", has_text=text).first.click()
    wait(page)


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    page.mouse.move(2, 2)  # ⓘ の説明などが出たままにならないように、カーソルを外す。
    wait(page, 300)
    page.screenshot(path=str(OUT / f"{name}.png"))
    print("wrote", name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    login = "help" + uuid.uuid4().hex[:8]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
        page.goto(args.base + "/")
        status = page.evaluate("""async login => (await fetch('/api/register', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({login_name: login, password: crypto.randomUUID()})})).status""", login)
        assert status == 201, status
        with sqlite3.connect(args.db) as db:
            db.execute("update users set is_catalog_author=1, is_app_admin=1 where name=?", (login,))
        # 承認の写真のために、Ps-01 の下書きを作って申請しておく。
        page.evaluate("""async () => {
            const api = (url, method = 'GET', body) => fetch(url, {method, headers: {'Content-Type': 'application/json'}, body: body && JSON.stringify(body)}).then(r => r.json());
            const draft = await api('/api/catalog/skill/drafts', 'POST', {target_id: 'Ps-01'});
            if (!draft.id || draft.status !== 'draft') return;  // 撮り直しで、もう申請済みのとき。
            const payload = {...draft.payload, 発動時効果: draft.payload.発動時効果.replace('出血]]5', '出血]]6'),
              特記処理: {...draft.payload.特記処理, effects: draft.payload.特記処理.effects.map(e => e.state_name === '出血' ? {...e, value: 6} : e)}};
            await api('/api/catalog/drafts/' + draft.id, 'PUT', {payload});
            await api('/api/catalog/drafts/' + draft.id + '/submit', 'POST', {});
        }""")

        open_workspace(page, args.base)
        shot(page, "01_browse")

        page.locator('[data-kind="skill"]').click(); wait(page, 1200)
        pick(page, "Ps-04"); wait(page, 1200)
        shot(page, "02_skill")

        page.locator('#cat-detail [data-action="edit"]').click(); wait(page, 1200)
        shot(page, "03_editor")

        page.locator('[data-section="effects"]').click(); wait(page)
        shot(page, "04_effects")

        value = page.locator('[data-effect-index="0"][data-effect-path="value"]').first
        value.fill("6"); value.dispatch_event("change"); wait(page)
        page.locator('[data-section="description"]').click(); wait(page)
        page.get_by_role("button", name="効果から文章を作る", exact=True).click(); wait(page)
        shot(page, "05_writer")

        page.locator('.cat-editbar [data-action="back"]').click(); wait(page)
        leave = page.get_by_role("button", name="変更を捨てる")
        if leave.count():
            leave.click(); wait(page)
        page.get_by_role("button", name="承認待ち").first.click(); wait(page)
        page.locator("[data-pending-id]").first.click(); wait(page, 1500)
        shot(page, "06_review")
        browser.close()


if __name__ == "__main__":
    main()
