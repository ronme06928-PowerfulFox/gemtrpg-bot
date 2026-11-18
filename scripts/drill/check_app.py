"""Exercise the real drill UI using only an explicitly selected disposable DB."""
import argparse
from pathlib import Path
import sqlite3
import uuid

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '_local' / 'drill_shots'


def api(page, path, body=None):
    result = page.evaluate("""async ({path,body}) => {
      const response=await fetch(path,{method:body === null ? 'GET' : 'POST',
        headers:{'Content-Type':'application/json'},body:body === null ? undefined : JSON.stringify(body)});
      return {status:response.status,data:await response.json()};
    }""", {'path': path, 'body': body})
    assert result['status'] < 400, result
    return result['data']


def ready(page):
    page.locator('.drill[data-drill-state="ready"]').wait_for()


def change(page, selector, value):
    with page.expect_response(lambda r: r.url.endswith('/api/drill/match')) as pending:
        page.locator(selector).fill(value)
    response = pending.value
    assert response.status == 200, response.text()
    ready(page)
    return response.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--base', default='http://127.0.0.1:5000')
    args = parser.parse_args()
    copied = Path(args.db).resolve()
    if copied.parent != (ROOT / '_local/agent_db').resolve() or not copied.is_file():
        parser.error('--db must be an existing disposable DB in _local/agent_db')
    OUT.mkdir(parents=True, exist_ok=True)
    errors, skill_counts = [], {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome')
        try:
            units = []
            for role in ('author', 'player'):
                context = browser.new_context(viewport={'width': 1280, 'height': 900})
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(args.base)
                name = 'drill_' + uuid.uuid4().hex[:8]
                api(page, '/api/register', {'login_name': name, 'password': uuid.uuid4().hex})
                with sqlite3.connect(copied) as connection:
                    user_id = connection.execute('SELECT id FROM users WHERE name=?', (name,)).fetchone()[0]
                    if role == 'author':
                        connection.execute('UPDATE users SET is_catalog_author=1 WHERE id=?', (user_id,))
                    connection.execute('INSERT INTO catalog_encounters(user_id,kind,entry_id,first_seen_at,room_name) VALUES (?,?,?,?,?)',
                                       (user_id, 'skill', 'E-00', '2026-11-19 00:00:00', 'drill_check'))
                if role == 'author':
                    for label, marks, visibility in [('解禁済みの魔物', ['known'], 'public'),
                                                      ('未遭遇の魔物', [], 'public'),
                                                      ('非公開の魔物', [], 'staff')]:
                        row = api(page, '/api/units/unit', {'visibility': visibility, 'payload': {
                            'name': label, 'allow_enemy': True, 'allow_ally': False, 'marks': marks,
                            'hp': 30, 'mp': 10, 'params': [{'label': '物理補正', 'value': 6}],
                            'skills': [{'id': 'E-00'}]}})['entry']
                        units.append(row['entry_id'])
                owned = api(page, '/api/owned_characters', {'kind': 'character', 'data': {
                    'name': '演習の冒険者', 'status': [{'label': 'HP', 'value': 20, 'max': 20},
                                              {'label': 'MP', 'value': 10, 'max': 10}],
                    'params': [{'label': '物理補正', 'value': 3}, {'label': '出身', 'value': 0}],
                    'commands': '4+1d2+1d{物理補正} 【Ps-00 基本の一太刀】', 'SPassive': [], 'inventory': {}}})['character']
                original = api(page, '/api/owned_characters/' + owned['id'])
                page.goto(args.base + '/#menu')
                page.reload()
                page.locator('[data-screen-card="drill"]').click()
                page.locator('[data-side="actor"] [data-source]').wait_for()
                assert page.url.endswith('#drill')
                actor = '[data-side="actor"] '
                target = '[data-side="target"] '
                page.locator(actor + '[data-source]').select_option('owned')
                page.locator(actor + '[data-record]').select_option(owned['id'])
                page.locator(actor + '[data-skill] option[value="Ps-00"]').wait_for(state='attached')
                page.locator(target + '[data-source]').select_option('unit')
                visible_units = page.locator(target + '[data-record] option').evaluate_all('rows=>rows.map(r=>r.value)')
                assert units[0] in visible_units
                assert (units[1] in visible_units) == (role == 'author')
                assert (units[2] in visible_units) == (role == 'author')
                with page.expect_response(lambda r: r.url.endswith('/api/drill/match')) as pending:
                    page.locator(target + '[data-record]').select_option(units[0])
                assert pending.value.status == 200, pending.value.text()
                ready(page)
                initial = pending.value.json()
                assert page.locator(target + '[data-skill]').input_value() == 'E-00'
                skill_counts[role] = page.locator(actor + '[data-skill] option[value^="E-"]').count()
                modified = change(page, actor + '[data-key="物理補正"]', '12')
                assert initial['win_rate'] != modified['win_rate'], (initial['win_rate'], modified['win_rate'])
                change(page, actor + '[data-key="物理補正"]', '3')
                assert api(page, '/api/owned_characters/' + owned['id']) == original
                assert page.locator('.drill-caution').is_visible()
                page.locator('.drill-caution').click()
                assert page.locator('.drill-caution li').count() > 0
                with page.expect_response(lambda r: r.url.endswith('/api/drill/match')) as pending:
                    page.locator(target + '[data-skill]').select_option('')
                assert pending.value.status == 200
                assert pending.value.json()['probabilities']['win'] == 1
                ready(page)
                with page.expect_response(lambda r: r.url.endswith('/api/drill/match')):
                    page.locator(target + '[data-skill]').select_option('E-00')
                ready(page)
                page.locator('[data-drill-scope]').select_option('on_win')
                assert page.locator('.drill-chart').count() == 4
                page.locator('[data-drill-scope]').select_option('on_lose')
                page.locator('[data-drill-scope]').select_option('all')
                with page.expect_response(lambda r: r.url.endswith('/api/drill/match')) as pending:
                    page.locator(actor + '[data-key="物理補正"]').fill('100001')
                assert pending.value.status == 422
                page.locator('.drill-result [role="alert"]').wait_for()
                assert '範囲外' in page.locator('.drill-result').inner_text() or '100000' in page.locator('.drill-result').inner_text()
                change(page, actor + '[data-key="物理補正"]', '3')
                # Exercise local buff editing without touching either source record.
                page.locator(actor + '.drill-buffs').evaluate("node=>node.closest('details').open=true")
                with page.expect_response(lambda r: r.url.endswith('/api/drill/match')) as pending:
                    page.locator(actor + '[data-add-buff]').click()
                assert pending.value.status == 200, pending.value.text()
                ready(page)
                change(page, actor + '[data-buff-field="value"]', '2')
                with page.expect_response(lambda r: r.url.endswith('/api/drill/match')):
                    page.locator(actor + '[data-remove-buff]').click()
                ready(page)
                assert api(page, '/api/owned_characters/' + owned['id']) == original
                if role == 'player':
                    page.locator('.drill-editor').evaluate_all('rows=>rows.forEach(row=>row.open=false)')
                    page.evaluate('scrollTo(0,0)')
                    page.screenshot(path=str(OUT / 'player-wide.png'), full_page=True, animations='disabled')
                    page.set_viewport_size({'width': 375, 'height': 900})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate('document.documentElement.scrollWidth')
                    page.screenshot(path=str(OUT / 'player-375.png'), full_page=True, animations='disabled')
                # Verify menu navigation destroys the mount and its pending calculations.
                page.get_by_role('button', name='← メインメニュー', exact=True).click()
                assert not page.locator('.drill').count()
                page.locator('[data-screen-card="drill"]').click()
                page.locator('[data-side="actor"] [data-source]').wait_for()
                context.close()
            assert skill_counts['author'] > skill_counts['player'] > 0, skill_counts
            assert not errors, errors
            print('Verified author/player visibility, owned vs unit, edits, one-sided attack, exclusions, 422, buffs, charts, cleanup and 375px.')
            print('Enemy skill choices:', skill_counts)
            print('Screenshots:', OUT)
        finally:
            browser.close()


if __name__ == '__main__':
    main()
