"""管理画面の使い方ページの写真を、本物のアプリから撮る（計画60 PR60-25 の試作）。

使い方：
  1. DB の写しでアプリを起動する：python app.py --db _local/agent_db/gemtrpg.db
  2. python scripts/catalog_preview/help/shots.py --base http://127.0.0.1:5000 --db _local/agent_db/gemtrpg.db
手元の instance/gemtrpg.db は指せない（AGENTS.md「手元のDBを守る」）。
写真は _local/catalog_preview/help/shots/ に、幅1280pxの画面から撮って書く。利用者は制作者とアプリ管理者の両方の印を付けて作る。
--publish を付けると、使い方ページ用の範囲に切り出して static/help/master_data/ に書く。
"""
import argparse
import sqlite3
import sys
import uuid
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from manager.local_db_guard import is_local_db  # noqa: E402
OUT = ROOT / "_local" / "catalog_preview" / "help" / "shots"
PUBLISHED = ROOT / "static" / "help" / "master_data"
# 試作の「要る所を切り出す」の範囲（1280×720、左・上・幅・高さ）。
CROPS = {
    "02_skill": (0, 122, 1280, 566),
    "04_effects": (168, 180, 592, 448),
    "05_writer": (168, 180, 592, 448),
    "06_review": (16, 122, 1250, 566),
}


def wait(page, ms=900):
    page.wait_for_timeout(ms)


def open_workspace(page, base):
    page.goto(base + "/#master")  # メインメニューの下の全幅の画面（E02 Part 18）
    page.reload()  # # だけの移動では読み込み直されず、登録したログインが画面に反映されないため。
    wait(page, 2500)


def pick(page, text):
    page.locator(".bo-workspace__record", has_text=text).first.click()
    wait(page)


def shot(page, name, *, publish, selector=None):
    output = PUBLISHED if publish else OUT
    output.mkdir(parents=True, exist_ok=True)
    page.mouse.move(2, 2)  # ⓘ の説明などが出たままにならないように、カーソルを外す。
    wait(page, 300)
    crop = CROPS.get(name) if publish else None
    clip = dict(zip(("x", "y", "width", "height"), crop)) if crop else None
    path = str(output / f"{name}.png")
    if selector:
        page.locator(selector).screenshot(path=path)
    else:
        page.screenshot(path=path, clip=clip)
    print("wrote", name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--db", required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if is_local_db(args.db):
        parser.error("手元の instance/gemtrpg.db は指せません。写しを python app.py --db で起動して、その写しを指してください。")
    capture = partial(shot, publish=args.publish)
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
        capture(page, "01_browse")

        page.locator('[data-kind="skill"]').click(); wait(page, 1200)
        pick(page, "Ps-04"); wait(page, 1200)
        capture(page, "02_skill")

        page.locator('#cat-detail [data-action="edit"]').click(); wait(page, 1200)
        capture(page, "03_editor")

        page.locator('[data-section="effects"]').click(); wait(page)
        capture(page, "04_effects")

        value = page.locator('[data-effect-index="0"][data-effect-path="value"]').first
        value.fill("6"); value.dispatch_event("change"); wait(page)
        page.locator('[data-section="description"]').click(); wait(page)
        page.get_by_role("button", name="効果から文章を作る", exact=True).click(); wait(page)
        capture(page, "05_writer")

        page.locator('.cat-editbar [data-action="back"]').click(); wait(page)
        leave = page.get_by_role("button", name="変更を捨てる")
        if leave.count():
            leave.click(); wait(page)
        page.get_by_role("button", name="承認待ち").first.click(); wait(page)
        page.locator("[data-pending-id]").first.click(); wait(page, 1500)
        capture(page, "06_review")

        page.set_viewport_size({"width": 1280, "height": 860})
        open_workspace(page, args.base)
        page.locator('[data-kind="skill"]').click()
        pick(page, "Ps-11")
        page.locator('#cat-metadata summary', has_text="参照している物").click()
        page.locator('#cat-metadata [data-target-kind="buff"][data-target="Bu-30"]').click()
        page.locator('#cat-detail [data-action="reference-back"]').wait_for()
        page.locator('#cat-detail summary', has_text="使われている所").click()
        page.locator('#cat-detail').evaluate('(detail) => { detail.scrollTop = 0; }')
        capture(page, "07_connections", selector="#cat-detail")

        # 印の図は公開済みの例を使う。書き換えるのは撮影用のDBだけ。
        page.evaluate("""async () => {
            const post = async (url, body, method = 'POST') => {
                const response = await fetch('/api/catalog/' + url, {method,
                    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
                if (!response.ok) throw new Error(await response.text());
                return response.json();
            };
            const draft = await post('buff/drafts', {target_id: 'Bu-30'});
            await post('drafts/' + draft.id, {payload: {...draft.payload, marks: ['enemy']}}, 'PUT');
            await post('drafts/' + draft.id + '/submit', {});
            await post('drafts/' + draft.id + '/approve', {});
        }""")
        page.set_viewport_size({"width": 1280, "height": 720})
        open_workspace(page, args.base)
        page.locator('[data-kind="buff"]').click()
        page.locator('[data-filter="mark"]').select_option('enemy')
        page.locator('#cat-detail [data-catalog-mark="enemy"]').wait_for()
        capture(page, "08_marks")
        page.locator('[data-filter="mark"]').select_option('')
        page.locator('[data-bulk-select="Bu-00"]').check()
        page.locator('[data-bulk-select="Bu-01"]').check()
        page.locator('[data-action="bulk-open"]').click()
        page.locator('[data-bulk-category]').select_option('特殊スタック')
        capture(page, "09_bulk")
        before = page.evaluate("fetch('/api/get_buff_data').then(r=>r.json())")
        page.locator('[data-bulk-confirm]').click()
        page.get_by_role('heading', name='公開 2件・飛ばした物 0件').wait_for()
        after = page.evaluate("fetch('/api/get_buff_data').then(r=>r.json())")
        for key in ('Bu-00','Bu-01'):
            assert after[key] == {**before[key], 'category':'特殊スタック'}
        page.locator('[data-bulk-close]').click()
        page.evaluate("""async () => {
            const data = await fetch('/api/catalog/buff').then(r=>r.json());
            const entries = data.entries.filter(row=>['Bu-00','Bu-01'].includes(row.entry_id))
                .map(row=>({entry_id:row.entry_id,base_revision:row.revision}));
            const response = await fetch('/api/catalog/buff/bulk',{method:'POST',
                headers:{'Content-Type':'application/json'},body:JSON.stringify({entries,changes:{category:'能力の増減'}})});
            if(!response.ok) throw new Error(await response.text());
        }""")
        page.locator('[data-filter="mark"]').select_option('enemy')
        pick(page, 'Bu-30')
        page.locator('#cat-detail [data-action="edit"]').click()
        page.locator('[data-mark="known"]').wait_for()
        capture(page, "09_known", selector="#cat-input-content")
        browser.close()


if __name__ == "__main__":
    main()
