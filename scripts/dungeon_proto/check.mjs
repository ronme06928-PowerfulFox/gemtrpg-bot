import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readdir, unlink, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const driver = execFileSync('python', ['-c',
  "from pathlib import Path; import playwright; print(Path(playwright.__file__).parent / 'driver' / 'package')",
], { encoding: 'utf8' }).trim();
const { chromium } = createRequire(import.meta.url)(driver);
const output = new URL('../../_local/dungeon_proto/', import.meta.url);
const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const screenshots = new Map();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => { if (/^https?:/.test(request.url())) errors.push(request.url()); });

const button = name => page.getByRole('button', { name, exact: true });
const variant = (key, value) => page.locator(`[data-compare="${key}"][data-value="${value}"]`);
const form = page.locator('#room-dialog form');
const notice = page.getByRole('status');
const shot = async name => {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name);
  if (process.argv.includes('--shots')) screenshots.set(name, await page.screenshot({ animations: 'disabled' }));
};

try {
  await page.goto(new URL('index.html', output).href);
  assert.equal(await page.locator('#menu-portal').getAttribute('data-theme'), 'paper');
  await shot('1280-menu.png');
  await page.locator('[data-screen-card="dungeon"]').click();
  assert.equal(new URL(page.url()).hash, '#dungeon');
  assert.equal(await page.locator('#menu-portal').getAttribute('data-theme'), 'abyss');
  assert.equal(await page.locator('.room-list-item').count(), 3);
  assert.match(await page.locator('.room-list-item').first().innerText(), /14F · T2/);
  assert.match(await page.locator('.room-list-item').nth(1).innerText(), /23F/);
  assert.match(await page.locator('.room-list-item').nth(2).innerText(), /待機中/);
  assert.equal(await page.locator('#contrast-results tr').count(), 17);
  assert.deepEqual(await page.locator('#contrast-results .fail th').allTextContents(), ['メニュー見出し']);
  await page.locator('#contrast-summary').click();
  assert(await page.locator('#contrast-results').isVisible());
  await page.locator('#contrast-summary').click();
  await shot('1280-rows.png');

  await variant('layout', 'cards').click();
  assert.equal(await page.locator('.tier-strip').count(), 3);
  assert.equal(await page.locator('.tier-strip [data-now]').getAttribute('data-tier'), '2');
  assert.equal(await page.locator('.tier-strip [data-record]').last().getAttribute('data-tier'), '3');
  assert.equal(await page.locator('.dungeon-hero').isVisible(), false);
  await variant('mood', 'hero').click();
  assert(await page.getByRole('heading', { name: 'アヌッサ・ホロウ' }).isVisible());
  await shot('1280-cards.png');
  await page.setViewportSize({ width: 680, height: 950 });
  await shot('680-cards.png');
  await page.setViewportSize({ width: 1280, height: 900 });

  await button('入る').first().click();
  assert.match(await notice.innerText(), /入室/);
  await variant('membership', 'empty').click();
  assert(await page.getByText('参加中の部屋はありません', { exact: true }).isVisible());
  await shot('1280-empty.png');
  await button('新しく作る').click();
  assert.equal(await form.locator('input').count(), 1);
  await shot('1280-create.png');
  await form.getByLabel('部屋名').fill('鉱床の門');
  await form.getByRole('button', { name: '作成', exact: true }).click();
  assert(await page.getByText('鉱床の門', { exact: true }).isVisible());
  await button('参加コードで入る').click();
  await form.getByLabel('参加コード').fill('WRONG-99');
  await form.getByRole('button', { name: '参加', exact: true }).click();
  assert(await form.getByText('参加コードが見つかりません', { exact: true }).isVisible());
  await shot('1280-code-error.png');
  await form.getByLabel('参加コード').fill('GEM-1423');
  await form.getByRole('button', { name: '参加', exact: true }).click();
  assert(await page.getByText('銀脈の遠征隊', { exact: true }).isVisible());
  assert.equal(await page.locator('.room-list-item').count(), 2);

  await variant('membership', 'sample').click();
  assert.equal(await page.locator('.room-list-item').count(), 3);
  await button('← メインメニュー').click();
  assert.equal(new URL(page.url()).hash, '#menu');
  await page.goBack();
  await page.locator('#dungeon').waitFor();
  assert.equal(await page.locator('.room-list-item').count(), 3);
  assert.deepEqual(errors, []);

  if (screenshots.size) {
    for (const name of await readdir(output)) {
      if (/^(1280|680)-[\w-]+\.png$/.test(name) && !screenshots.has(name)) await unlink(new URL(name, output));
    }
    for (const [name, data] of screenshots) await writeFile(new URL(name, output), data);
  }
  console.log(`OK: interactions, 17 contrast pairs, widths, ${screenshots.size} screenshots`);
  console.log(await page.locator('#contrast-summary').textContent());
} finally {
  await browser.close();
}
