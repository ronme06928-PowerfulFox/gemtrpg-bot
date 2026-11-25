"""Verify the deployed bundle against the disposable PR35-2 database."""

import argparse
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "_local/agent_db/gemtrpg.db"
OUT = ROOT / "_local/pr35_2_shots"
BASE = "http://127.0.0.1:5000"
UNITS = "/api/units"

CONTRAST = """checks => {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext('2d', {willReadFrequently:true});
  function rgb(color) {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, 1, 1);
    return [...ctx.getImageData(0, 0, 1, 1).data];
  }
  function background(node) {
    const value = rgb(getComputedStyle(node).backgroundColor);
    return value[3] ? value : background(node.parentElement);
  }
  const luminance = ([r,g,b]) => [r,g,b].map(v => v / 255)
    .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
    .reduce((sum, v, i) => sum + v * [.2126,.7152,.0722][i], 0);
  return checks.map(([selector, edge]) => {
    const node = document.querySelector(selector);
    if (!node || !node.getClientRects().length) throw Error(selector);
    const style = getComputedStyle(node);
    const backgroundNode = edge ? node.parentElement : node;
    const ink = luminance(rgb(style[edge || 'color']));
    const surface = background(backgroundNode);
    // Cover the darkest and lightest stops used by the shared button gloss.
    const surfaces = [surface];
    if (!edge && style.backgroundImage !== 'none') {
      const shade = Number(style.getPropertyValue('--ui-shade'));
      const sheen = node.classList.contains('cat-primary') ? 31 / 255 : Number(style.getPropertyValue('--ui-sheen'));
      surfaces.push(surface.map(v => v * (1 - shade)), surface.map(v => v * (1 - sheen) + 255 * sheen));
    }
    return [selector, Math.min(...surfaces.map(surface => {
      const lum = luminance(surface);
      return (Math.max(ink, lum) + .05) / (Math.min(ink, lum) + .05);
    })), edge ? 3 : 4.5];
  });
}"""


def api(page, method, url, **body):
    response = page.request.fetch(url, method=method, data=body if body else None)
    assert response.ok, f"{method} {url}: {response.status} {response.text()}"
    return response.json()


def register(browser, name, *, author=False):
    page = browser.new_page(base_url=BASE, viewport={"width": 1280, "height": 860})
    api(page, "POST", "/api/register", login_name=name, password=uuid4().hex)
    if author:
        with sqlite3.connect(DB) as connection:
            result = connection.execute("UPDATE users SET is_catalog_author=1 WHERE name=?", (name,))
            assert result.rowcount == 1
    return page


def select_unit(page, entry_id):
    page.locator(f'.unit-records [data-id="{entry_id}"]').click()
    expect(page.locator('.unit-detail-header .cat-id')).to_have_text(entry_id)
    return page.locator('.unit-section [data-path="name"]')


def click(page, text):
    page.get_by_role("button", name=text, exact=True).click()


def create_in_workspace(page, kind, name):
    page.locator(f'.unit-tabs [data-kind="{kind}"]').click()
    click(page, "＋ 新規")
    if kind in ("unit", "formation"):
        click(page, "空のユニット" if kind == "unit" else "敵編成")
    page.locator('.unit-section [data-path="name"]').fill(name)
    if kind == "unit":
        tag = page.locator("[data-unit-tag-input]")
        tag.fill("等級:鉄級")
        tag.press("Enter")
    with page.expect_response(lambda response: response.request.method == "POST"
                              and urlsplit(response.url).path == f"{UNITS}/{kind}") as save:
        click(page, "保存")
    assert save.value.status == 201, save.value.text()
    entry = save.value.json()["entry"]
    assert entry["payload"]["domain"] == "hollow"
    expect(page.locator(".unit-detail-header .cat-id")).to_have_text(entry["entry_id"])


def verify(browser):
    token = uuid4().hex[:8]
    page = register(browser, f"PR352Author{token}", author=True)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    session_unit = api(page, "POST", f"{UNITS}/unit", payload={
        "domain": "session", "name": "街道の番兵", "hp": 45, "tags": ["等級:鉄級"],
    })["entry"]["entry_id"]
    hollow_unit = api(page, "POST", f"{UNITS}/unit", payload={
        "domain": "hollow", "name": "晶牙の人狼", "hp": 56, "tags": ["等級:銀級"],
        "skills": [{"id": "Ps-01", "name": ""}],
    })["entry"]["entry_id"]
    staff_unit = api(page, "POST", f"{UNITS}/unit", visibility="staff", payload={
        "domain": "hollow", "name": "伏せた守衛", "tags": ["等級:銅級"],
    })["entry"]["entry_id"]
    refs = api(page, "GET", "/api/catalog/skill/Ps-01/references")["references"]
    assert any(ref["entry_id"] == hollow_unit and ref.get("domain") == "hollow" for ref in refs)
    photos = {}
    contrasts = []
    page.goto(BASE + "/#menu")
    expect(page.locator(".menu-data-button")).to_have_text(["ユニット管理", "マスターデータ", "ホロウデータ"])
    expect(page.locator(".app-loading")).to_be_hidden()
    contrasts += page.evaluate(CONTRAST, [
        ['.menu-data-button[data-theme="abyss"]', None],
        ['.menu-data-button[data-theme="abyss"]', "borderTopColor"],
    ])
    photos["01-menu.png"] = page.screenshot()
    click(page, "ホロウデータ")
    expect(page.locator('.unit-workspace')).to_have_attribute("data-theme", "abyss")
    expect(page.locator(".unit-tab-group h3")).to_have_text(["敵", "階", "報酬"])
    expect(page.locator(".unit-tab-group button:not(:disabled)")).to_have_count(4)
    expect(page.locator(".unit-tab-group button:disabled")).to_have_count(8)
    expect(page.locator(f'.unit-records [data-id="{session_unit}"]')).to_have_count(0)
    expect(page.locator(f'.unit-records [data-id="{staff_unit}"]')).to_be_visible()
    name = select_unit(page, hollow_unit)
    expect(name).to_have_value("晶牙の人狼")
    photos["02-hollow-list.png"] = page.screenshot()
    name.fill("晶牙の人狼・改")
    click(page, "← メインメニュー")
    click(page, "編集に戻る")
    expect(name).to_have_value("晶牙の人狼・改")
    page.evaluate("history.back()")
    click(page, "編集に戻る")
    expect(page).to_have_url(BASE + "/#hollow-data")
    expect(name).to_have_value("晶牙の人狼・改")
    contrasts += page.evaluate(CONTRAST, [
        [".unit-workspace h2", None],
        [".unit-confirm-heading h3", None],
        [".unit-toc [aria-current=true]", None],
        [".unit-section .cat-field", None],
        [".unit-tab-group h3", None],
        [".unit-section [data-path=name]", None],
        [".unit-footer .cat-primary", None],
        [".unit-tabs [aria-pressed=true]", None],
        [".unit-records .is-selected strong", None],
        [".unit-tabs [aria-pressed=true]", "borderTopColor"],
        [".unit-section [data-path=name]", "borderTopColor"],
        [".unit-filters input[type=search]", "borderTopColor"],
        [".unit-records .is-selected", "borderBottomColor"],
        [".unit-footer .cat-primary", "borderTopColor"],
        [".screen-back", "borderTopColor"],
    ])
    photos["03-hollow-edit.png"] = page.screenshot()
    click(page, "保存")
    expect(page.locator(".cat-message")).to_have_text("保存しました。")
    assert api(page, "GET", f"{UNITS}/unit/{hollow_unit}")["payload"]["name"] == "晶牙の人狼・改"
    photos["03b-hollow-saved.png"] = page.screenshot()
    for kind, name in [("unit", "灰殻の小人"), ("formation", "鉱脈の群れ"),
                       ("stage", "鉱脈の行き止まり"), ("unit_collection", "鉱脈層")]:
        create_in_workspace(page, kind, name)

    click(page, "← メインメニュー")
    click(page, "ユニット管理")
    name = select_unit(page, session_unit)
    expect(page.locator(f'.unit-records [data-id="{hollow_unit}"]')).to_have_count(0)
    expect(page.locator(".unit-check")).to_have_text("問題はありません。")
    page.locator(".unit-more summary").click()
    photos["04-session-copy.png"] = page.screenshot()
    page.locator(".unit-more summary").click()
    name.fill("保存していない入力")
    page.locator(".unit-more summary").click()
    click(page, "ホロウへ複製")
    expect(page.locator(".cat-message")).to_contain_text("保存するか破棄")
    click(page, "変更を破棄")
    page.locator("#app-dialog-confirm").click()
    expect(name).to_have_value("街道の番兵")
    page.locator(".unit-more summary").click()
    with page.expect_response(lambda response: response.request.method == "POST"
                              and response.url.endswith("/duplicate-to-hollow")) as copy:
        click(page, "ホロウへ複製")
    assert copy.value.status == 201, copy.value.text()
    copied = copy.value.json()["entry"]
    assert copied["payload"]["domain"] == "hollow"
    expect(page.locator(".cat-message")).to_be_visible()
    expect(page.locator(".cat-message")).to_contain_text("「ホロウデータ」で開けます")
    photos["05-copy-notice.png"] = page.screenshot()
    click(page, "← メインメニュー")
    click(page, "ホロウデータ")
    expect(select_unit(page, copied["entry_id"])).to_have_value("街道の番兵")
    expect(page.locator(f'.unit-records [data-id="{session_unit}"]')).to_have_count(0)
    expect(page.locator(".unit-check")).to_have_text("問題はありません。")
    photos["06-hollow-copy.png"] = page.screenshot()

    reader = register(browser, f"PR352Reader{token}")
    reader.goto(BASE + "/#hollow-data")
    expect(reader.locator(f'.unit-records [data-id="{hollow_unit}"]')).to_be_visible()
    expect(reader.locator(f'.unit-records [data-id="{staff_unit}"]')).to_have_count(0)
    expect(select_unit(reader, hollow_unit)).to_be_disabled()
    expect(reader.get_by_role("button", name="保存", exact=True)).to_have_count(0)
    assert not errors, errors
    failures = [(label, ratio) for label, ratio, minimum in contrasts if ratio < minimum]
    assert not failures, failures
    print("Contrast: " + ", ".join(f"{selector} {ratio:.2f}:1" for selector, ratio, _ in contrasts))
    return photos


def launch_and_verify(app_python):
    assert DB.is_file() and DB.resolve() == DB, "Prepare the disposable DB"
    with socket.socket() as probe:
        if os.name == "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", 5000))
        except OSError as exc:
            raise RuntimeError("Port 5000 must be available for the verification app") from exc
    env = {**os.environ, "AI_AGENT": "1", "PYTHONUTF8": "1"}
    for key in ("GEMTRPG_DB", "GEMTRPG_SKIP_IMPORT_STARTUP", "GEMTRPG_ALLOW_LOCAL_DB"):
        env.pop(key, None)
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(
            [app_python, "app.py", "--db", str(DB)], cwd=ROOT, env=env,
            stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and proc.poll() is None:
                try:
                    with urlopen(BASE + "/healthz", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("The verification app did not start")
            expect.set_options(timeout=15000)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome")
                photos = verify(browser)
                browser.close()
                return photos
        except Exception:
            log.seek(0)
            print("\n".join(log.read().decode("utf-8", errors="replace").splitlines()[-16:]), file=sys.stderr)
            raise
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, photo in photos.items():
        (OUT / name).write_bytes(photo)
    print(f"Saved {len(photos)} images in {OUT}")
