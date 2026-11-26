"""Verify the Tier and encounter editors in the app against the disposable agent database."""
import argparse
import sys
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, CONTRAST, ROOT, UNITS, api, click, launch_and_verify, register, select_unit


def create(page, kind, **payload):
    return api(page, "POST", f"{UNITS}/{kind}", payload={"domain": "hollow", **payload})["entry"]["entry_id"]


def verify(browser):
    page = register(browser, "PR354Author" + uuid4().hex[:8], author=True)
    errors = []
    photos = {}
    page.on("pageerror", lambda error: errors.append(str(error)))
    formations = []
    for name, units in (
        ("入口の群れ", [("岩牙", "鉄級", 3), ("晶殻", "銅級", 1), ("銀角", "銀級", 2)]),
        ("淵門の守り手", [("金爪", "金級", 2), ("虚晶", "特異級", 1)]),
    ):
        members = [{"unit_id": create(page, "unit", name=unit, tags=[f"等級:{grade}"]), "count": count}
                   for unit, grade, count in units]
        formations.append(create(page, "formation", name=name, type="enemy", members=members))
    ally = create(page, "formation", name="味方編成", type="ally", members=[])
    session = api(page, "POST", f"{UNITS}/formation",
                  payload={"domain": "session", "name": "セッション編成", "type": "enemy", "members": []})
    stage = create(page, "stage", name="淵門の祭壇", enemy_formation_id=formations[1])

    def field(path):
        return page.locator(f'.unit-section [data-path="{path}"]')

    def tab(kind):
        page.locator(f'.unit-tabs [data-kind="{kind}"]').click()

    def section(key):
        page.locator(f'.unit-toc [data-section="{key}"]').click()

    def shot(name):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        expect(page.locator(".unit-check")).to_have_text("問題はありません。")
        expect(page.locator(".cat-message")).to_be_hidden()
        photos[name] = page.screenshot(animations="disabled")

    def save(kind):
        with page.expect_response(lambda response: response.request.method == "POST"
                                  and urlsplit(response.url).path == f"{UNITS}/{kind}") as request:
            click(page, "保存")
        assert request.value.status == 201, request.value.text()
        return request.value.json()["entry"]

    page.goto(BASE + "/#hollow-data")
    expect(page.locator(".unit-workspace:not([aria-busy])")).to_be_visible()
    tab("tier")
    click(page, "＋ 新規")
    field("name").fill("入穴")
    field("tier").fill("6")
    expect(page.locator('[data-unit-field-error="tier"]')).to_have_text("値の型または範囲が不正です")
    field("tier").fill("1")
    field("description").fill("古坑道の先に鉄色の洞が開く。")
    field("hp_multiplier").fill("1.2")
    field("attack_multiplier").fill("1.1")
    tier = save("tier")
    assert tier["payload"]["tier"] == 1
    tab("hollow_map")
    click(page, "＋ 新規")
    field("name").fill("淵門の坑道")
    field("boss_formation_id").select_option(formations[1])
    field("boss_stage_id").select_option(stage)
    section("events")
    for key, weight in zip(("normal", "elite", "chest", "miasma"), ("40", "10", "20", "10")):
        field(f"event_weights.{key}").fill(weight)
    expect(page.locator('[data-event-share="normal"]')).to_have_text("50%")
    measurements = page.evaluate(CONTRAST, [
        [f'[data-event-share="{key}"]', None] for key in ("normal", "elite", "chest", "miasma")
    ] + [[".unit-event-strip", "borderTopColor"], [".unit-event-fields input", "borderTopColor"]])
    shot("1280-map-weights.png")
    section("encounters")
    click(page, "＋ 通常を追加")
    first = field("encounters.normal.0.formation_id")
    expect(first.locator(f'option[value="{ally}"]')).to_have_count(0)
    expect(first.locator(f'option[value="{session["entry"]["entry_id"]}"]')).to_have_count(0)
    first.select_option(formations[0])
    field("encounters.normal.0.weight").fill("30")
    click(page, "＋ 通常を追加")
    field("encounters.normal.1.formation_id").select_option(formations[1])
    field("encounters.normal.1.weight").fill("10")
    click(page, "＋ 精鋭を追加")
    field("encounters.elite.0.formation_id").select_option(formations[1])
    expect(page.locator("[data-encounter-share]").first).to_have_text("75%")
    expect(page.locator(".unit-encounter-members").first).to_contain_text("岩牙×3")
    expect(page.locator(".unit-check")).to_have_text("問題はありません。")
    area = save("hollow_map")
    assert area["payload"]["encounters"]["normal"][0]["weight"] == 30
    expect(field("encounters.normal.0.weight")).to_have_value("30")
    shot("1280-map-encounters.png")

    section("basic")
    field("name").fill("未保存の変更")
    tab("fixed_floor")
    expect(page.locator("#app-dialog-confirm")).to_be_visible()
    page.keyboard.press("Escape")
    expect(field("name")).to_have_value("未保存の変更")
    tab("fixed_floor")
    page.locator("#app-dialog-confirm").click()
    click(page, "＋ 新規")
    field("name").fill("入穴の番人")
    field("floor").fill("10")
    field("type").select_option("camp")
    expect(field("stage_id")).to_have_count(0)
    field("text").fill("焚き火が残っている。")
    expect(page.locator(".unit-check")).to_have_text("問題はありません。")
    fixed = save("fixed_floor")
    expect(page.locator(f'.unit-records [data-id="{fixed["entry_id"]}"]')).to_contain_text("T1 · 10F")
    shot("1280-fixed-floor.png")

    tab("tier")
    expect(select_unit(page, tier["entry_id"])).to_have_value("入穴")
    tab("hollow_map")
    expect(select_unit(page, area["entry_id"])).to_have_value("淵門の坑道")
    section("encounters")
    expect(field("encounters.normal.0.weight")).to_have_value("30")
    measurements += page.evaluate(CONTRAST, [
        [f'.unit-grade[data-grade="{grade}"]', edge]
        for grade in ("iron", "copper", "silver", "gold", "exceptional") for edge in (None, "borderTopColor")
    ] + [
        [".unit-encounter-row select", None],
        [".unit-encounter-row select", "borderTopColor"],
        ["[data-encounter-share]", None],
        [".unit-footer .cat-primary", None],
    ])
    assert all(ratio >= minimum for _, ratio, minimum in measurements), measurements
    page.set_viewport_size({"width": 680, "height": 900})
    shot("680-map.png")

    tab("fixed_floor")
    expect(select_unit(page, fixed["entry_id"])).to_have_value("入穴の番人")
    expect(field("type")).to_have_value("camp")
    click(page, "← メインメニュー")
    click(page, "ユニット管理")
    expect(page.locator('.unit-tabs [data-kind="tier"], .unit-tabs [data-kind="hollow_map"], .unit-tabs [data-kind="fixed_floor"]')).to_have_count(0)
    assert not errors, errors
    print("Contrast: " + ", ".join(f"{label} {ratio:.2f}:1" for label, ratio, _ in measurements))
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python, exercise=verify)
    output = ROOT / "_local/pr35_4_shots"
    output.mkdir(parents=True, exist_ok=True)
    for width in (1280, 680):
        for old in output.glob(f"{width}-*.png"):
            if old.name not in photos:
                old.unlink()
    for name, photo in photos.items():
        (output / name).write_bytes(photo)
    print(f"Saved {len(photos)} images in {output}")
