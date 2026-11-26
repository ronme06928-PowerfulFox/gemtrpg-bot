"""Save and reopen the Hollow map, Tier and fixed floor editors on a DB copy."""

import argparse
import sys
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import expect

from scripts.hollow_data_proto.check_app import BASE, ROOT, UNITS, api, click, launch_and_verify, register


def verify(browser):
    page = register(browser, f"MapEditor{uuid4().hex[:8]}", author=True)
    photos = {}

    def tab(kind):
        expect(page.locator(".unit-workspace:not([aria-busy])")).to_be_visible()
        control = page.locator(f'.unit-tabs [data-kind="{kind}"]')
        control.click()
        expect(control).to_have_attribute("aria-pressed", "true")

    def section(name):
        page.locator(f'.unit-toc [data-section="{name}"]').click()

    def field(path):
        return page.locator(f'.unit-section [data-path="{path}"]')

    def save(kind, entry_id=None):
        url = f"{UNITS}/{kind}" + (f"/{entry_id}" if entry_id else "")
        method = "PUT" if entry_id else "POST"
        with page.expect_response(lambda response: response.request.method == method
                                  and urlsplit(response.url).path == url) as result:
            click(page, "保存")
        response = result.value
        assert response.status == (200 if entry_id else 201), response.text()
        row = response.json()["entry"]
        expect(page.locator(".unit-detail-header .cat-id")).to_have_text(row["entry_id"])
        expect(page.locator("[data-unit-revision]")).to_have_text(f"版 {row['revision']}")
        return row

    maps = api(page, "GET", f"{UNITS}/hollow_map?domain=hollow")["entries"]
    seed = next(row["payload"] for row in maps if row["payload"]["name"] == "試遊 青晶洞")
    page.goto(BASE + "/#hollow-data")
    tab("hollow_map")
    click(page, "＋ 新規")
    expect(page.locator(".unit-detail-header .cat-id")).to_have_text("新規")
    field("name").fill("確認用の青晶洞")
    field("tier").fill("4")
    field("description").fill("再読み込み用の説明")
    field("boss_formation_id").select_option(seed["boss_formation_id"])
    field("boss_stage_id").select_option(seed["boss_stage_id"])
    section("events")
    field("event_weights.normal").fill("4")
    field("event_weights.chest").fill("2")
    section("encounters")
    click(page, "＋ 通常を追加")
    field("encounters.normal.0.formation_id").select_option(seed["encounters"]["normal"][0]["formation_id"])
    expect(page.locator(".unit-encounter-members")).to_contain_text("鉄級")
    section("categories")
    expect(page.locator('.unit-section [data-path^="category_weights."]')).to_have_count(12)
    field("category_weights.出血").fill("3")
    row = save("hollow_map")
    map_id = row["entry_id"]
    click(page, "再読み込み")
    expect(field("category_weights.出血")).to_have_value("3")
    photos["02-map-categories.png"] = page.screenshot()
    section("basic")
    expect(field("boss_formation_id")).to_have_value(seed["boss_formation_id"])
    expect(field("boss_stage_id")).to_have_value(seed["boss_stage_id"])
    expect(field("tier")).to_have_value("4")
    expect(page.locator(".unit-records button").last).to_have_attribute("data-id", map_id)
    photos["01-map.png"] = page.screenshot()
    section("encounters")
    expect(field("encounters.normal.0.formation_id")).to_have_value(seed["encounters"]["normal"][0]["formation_id"])
    photos["03-map-encounters.png"] = page.screenshot()

    tab("tier")
    tier_id = page.locator(".unit-records [data-id]").first.get_attribute("data-id")
    page.locator(f'.unit-records [data-id="{tier_id}"]').click()
    expect(page.locator("[data-section=events], [data-section=encounters]")).to_have_count(0)
    field("description").fill("Tier の説明を保存")
    save("tier", tier_id)
    photos["04-tier.png"] = page.screenshot()

    tab("fixed_floor")
    click(page, "＋ 新規")
    field("name").fill("確認用の先人のキャンプ")
    field("floor").fill("45")
    field("type").select_option("camp")
    expect(field("type").locator("option")).to_have_text(["町", "キャンプ"])
    field("text").fill("焚き火が残っている")
    save("fixed_floor")
    photos["05-fixed-floor.png"] = page.screenshot()
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    photos = launch_and_verify(parser.parse_args().app_python, exercise=verify)
    output = ROOT / "_local/pr35_10_shots"
    output.mkdir(parents=True, exist_ok=True)
    for name, data in photos.items():
        (output / name).write_bytes(data)
    print(f"Saved {len(photos)} screenshots in {output}")
