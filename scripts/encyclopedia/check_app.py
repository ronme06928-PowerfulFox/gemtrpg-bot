"""Verify the real encyclopedia at 1280px using an explicitly selected copied DB."""
import argparse
from pathlib import Path
import sqlite3
import uuid

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "_local" / "encyclopedia_check"


def api(page, path, method="GET", body=None):
    result = page.evaluate("""async ({path,method,body}) => {
      const response = await fetch(path, {method, headers:{'Content-Type':'application/json'},
        body:body === null ? undefined : JSON.stringify(body)});
      return {status:response.status, data:await response.json()};
    }""", dict(path=path, method=method, body=body))
    assert result["status"] < 400, result
    return result["data"]



def assert_contrast(page):
    failures = page.locator(".encyclopedia").evaluate("""root => {
      const rgb = text => text.match(/[\d.]+/g).map(Number);
      const lum = c => c.slice(0,3).map(x => (x/=255) <= .04045 ? x/12.92 : ((x+.055)/1.055)**2.4)
        .reduce((sum,x,i)=>sum+x*[.2126,.7152,.0722][i],0);
      const ratio = (a,b) => (Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
      function background(node) {
        const c = rgb(getComputedStyle(node).backgroundColor);
        return c[3] === 0 ? background(node.parentElement) : c;
      }
      const failed=[];
      for(const node of root.querySelectorAll('*')) {
        if(!node.getClientRects().length || node instanceof SVGElement) continue;
        const style=getComputedStyle(node);
        const text=[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE && child.textContent.trim());
        if(text && !node.closest('button:disabled:not(.locked)')) {
          const contrast=ratio(rgb(style.color),background(node));
          if(contrast<4.5) failed.push([node.className,node.textContent.slice(0,30),contrast]);
        }
        if(node.matches('button:not(:disabled),input,summary,.locked,.clasp,.door,.open-book,#chapter-tabs button')) {
          const contrast=ratio(rgb(style.borderTopColor),background(node.parentElement));
          if(contrast<3) failed.push(['border',node.className,contrast]);
        }
      }
      return failed;
    }""")
    assert not failures, failures

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    copied = Path(args.db).resolve()
    allowed = (ROOT / "_local" / "agent_db").resolve()
    if copied.parent != allowed or not copied.is_file():
        parser.error("--db must select an existing copied DB in _local/agent_db")
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        try:
            for role in ("player", "author"):
                context = browser.new_context(viewport={"width":1280, "height":800})
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(args.base)
                name = "encyclopedia_" + uuid.uuid4().hex[:8]
                api(page, "/api/register", "POST", {"login_name":name, "password":uuid.uuid4().hex})
                with sqlite3.connect(copied) as connection:
                    user_id = connection.execute("SELECT id FROM users WHERE name=?", (name,)).fetchone()[0]
                    connection.execute(
                        "INSERT INTO catalog_encounters(user_id,kind,entry_id,first_seen_at,room_name) VALUES (?,?,?,?,?)",
                        (user_id,"skill","E-00","2026-11-18 00:00:00","encyclopedia_check"))
                    if role == "author":
                        connection.execute("UPDATE users SET is_catalog_author=1 WHERE id=?", (user_id,))
                page.goto(args.base + "/#encyclopedia")
                page.reload()
                page.locator('.encyclopedia [data-door="adventurers"]').wait_for()
                page.wait_for_function("typeof socket !== 'undefined' && socket.connected")
                assert page.locator(".encyclopedia .door").count() == 4
                assert page.locator("[data-own-encounters]").count() == (1 if role == "author" else 0)

                def shot(scene):
                    page.locator(".app-loading").wait_for(state="hidden")
                    page.mouse.move(2, 2)
                    assert_contrast(page)
                    page.screenshot(path=str(OUT / f"{role}-{scene}.png"), animations="disabled")

                shot("doors")
                palettes, sizes = [], []
                for door in ("adventurers", "monsters", "world"):
                    page.locator(f'[data-door="{door}"]').click()
                    records = page.locator(".shelf-book").evaluate_all("""books => books.map(book => ({
                      color:getComputedStyle(book).getPropertyValue('--jewel'),
                      size:[book.offsetWidth,book.offsetHeight]
                    }))""")
                    palettes.extend(row["color"] for row in records)
                    sizes.extend(tuple(row["size"]) for row in records)
                    assert_contrast(page)
                    page.locator('#close-shelf').click()
                assert len(palettes) == len(set(palettes)) == 16
                assert set(sizes) == {(80,278)}
                page.locator('[data-door="adventurers"]').click()
                page.locator('.shelf-book[data-book="Ps"]').wait_for()
                shot("shelf")
                page.locator('[data-book="Ps"]').click()
                page.locator('[data-entry="Ps-04"]').click()
                page.locator(".book-reading-body .skill-detail-command").wait_for()
                shot("skill")
                assert page.locator(".encounter-date").count() == 0
                original_page = page.locator("#page-number").inner_text().split("/")[0]
                page.get_by_role("button", name="次へ", exact=True).click()
                page.wait_for_function("!document.querySelector('.turn-leaf').dataset.direction")
                assert page.locator(".specimen-id").inner_text() != "Ps-04"
                page.locator("#page-number").click()
                page.get_by_label("移動先のページ").fill(original_page)
                page.get_by_role("button", name="移動", exact=True).click()
                assert page.locator(".specimen-id").inner_text() == "Ps-04"
                page.get_by_role("button", name="目次へ戻る", exact=True).click()
                assert page.locator(".contents-entry.highlighted").get_attribute("data-entry") == "Ps-04"
                page.locator('#close-book').click()
                page.locator('#close-shelf').click()
                page.locator('[data-door="monsters"]').click()
                page.locator('[data-book="E"]').click()
                assert page.locator(".contents-entry.locked").count() > 0 if role == "player" else page.locator(".contents-entry.locked").count() == 0
                shot("enemy")
                page.locator('.contents-entry[data-entry="E-00"]').click()
                assert "2026" in page.locator(".encounter-date").inner_text()
                page.locator('#close-book').click()
                page.locator('#close-shelf').click()
                page.locator('[data-door="world"]').click()
                page.locator('[data-book="glossary"]').click()
                page.get_by_role("button", name="タイミング", exact=True).click()
                assert page.locator('#chapter-tabs [aria-current]').inner_text() == "タイミング"
                shot("chapter")
                page.locator('#close-book').click()
                page.locator('#query').fill("出血")
                assert page.locator('#search-results button').count() > 1
                shot("search")
                page.locator('#search-results button:not(:disabled)').first.click()
                assert page.locator("#book-window").is_visible()
                page.locator('#close-book').click()
                if role == "author":
                    page.locator("[data-own-encounters]").check()
                    page.locator('#query').fill("E-01")
                    assert page.locator('#search-results [data-entry="E-01"]').is_disabled()
                    page.locator("[data-own-encounters]").uncheck()
                    page.locator('#query').fill("E-01")
                    assert not page.locator('#search-results [data-entry="E-01"]').is_disabled()
                if role == "author":
                    unit = api(page, "/api/units/unit", "POST", {"payload":{
                        "name":"図鑑の確認用", "allow_enemy":True, "allow_ally":False, "marks":["known"]}})
                    unit_id = unit["entry"]["entry_id"]
                    page.goto(args.base + "/#units")
                    page.locator('[data-filter="mark"]').select_option("known")
                    page.locator(f'[data-unit-action="record"][data-id="{unit_id}"]').click()
                    page.locator('[data-unit-mark="known"]').uncheck()
                    page.get_by_role("button", name="保存", exact=True).click()
                    page.wait_for_function("document.querySelector('.unit-workspace')?.getAttribute('aria-busy') !== 'true' && document.querySelector('.unit-dirty')?.textContent === ''")
                    page.wait_for_function("id => fetch('/api/units/unit/'+id).then(r=>r.json()).then(d=>!d.payload.marks.includes('known'))", arg=unit_id)
                    page.locator('[data-unit-mark="known"]').check()
                    page.get_by_role("button", name="保存", exact=True).click()
                    page.wait_for_function("document.querySelector('.unit-workspace')?.getAttribute('aria-busy') !== 'true' && document.querySelector('.unit-dirty')?.textContent === ''")
                    page.wait_for_function("id => fetch('/api/units/unit/'+id).then(r=>r.json()).then(d=>d.payload.marks.includes('known'))", arg=unit_id)
                    page.locator('[data-path="allow_enemy"]').uncheck()
                    assert page.locator('[data-unit-mark="known"]').count() == 0
                    page.locator('[data-path="allow_enemy"]').check()
                    page.get_by_role("button", name="保存", exact=True).click()
                    page.wait_for_function("document.querySelector('.unit-workspace')?.getAttribute('aria-busy') !== 'true' && document.querySelector('.unit-dirty')?.textContent === ''")
                    page.wait_for_function("id => fetch('/api/units/unit/'+id).then(r=>r.json()).then(d=>d.payload.allow_enemy)", arg=unit_id)
                    page.goto(args.base + "/#master")
                    page.locator('[data-kind="skill"]').click()
                    page.locator('[data-skill-category="E"]').click()
                    page.get_by_role("button", name="＋新しく作る", exact=True).click()
                    page.get_by_role("button", name="編集を始める", exact=True).click()
                    page.locator('[data-mark="known"]').wait_for()
                    page.locator('[data-action="back"]').first.click()
                    page.locator('[data-skill-category="Ps"]').click()
                    page.get_by_role("button", name="＋新しく作る", exact=True).click()
                    page.get_by_role("button", name="編集を始める", exact=True).click()
                    assert page.locator('[data-mark="known"]').count() == 0
                    page.locator('[data-action="back"]').first.click()
                # Exercise destruction and mounting again through the normal menu.
                page.get_by_role("button", name="← メインメニュー", exact=True).click()
                page.locator('[data-screen-card="encyclopedia"]').click()
                page.locator('.encyclopedia [data-door="adventurers"]').wait_for()
                context.close()
            assert errors == [], errors
            print("Verified player/author doors, shelf, locked entries, skills, chapters, search, author preview and remount.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
