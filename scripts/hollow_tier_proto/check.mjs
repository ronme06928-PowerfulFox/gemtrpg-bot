import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readdir, unlink, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const driver = execFileSync('python', ['-c',
  "from pathlib import Path; import playwright; print(Path(playwright.__file__).parent / 'driver' / 'package')",
], { encoding: 'utf8' }).trim();
const { chromium } = createRequire(import.meta.url)(driver);
const output = new URL('../../_local/hollow_tier_proto/', import.meta.url);
const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
const errors = [];
const shots = new Map();
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => { if (/^https?:/.test(request.url())) errors.push(request.url()); });

const button = name => page.getByRole('button', { name, exact: true });
const field = key => page.locator(`[name="${key}"]`);
const normal = page.locator('[data-encounters="normal"]');
const map = page.locator('.floor-map');
const switchTo = (group, variant) => page.locator(`[data-compare="${group}"][data-value="${variant}"]`).click();
const shot = async name => {
  await page.evaluate(() => {
    document.activeElement.blur();
    window.scrollTo(0, 0);
  });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name);
  if (process.argv.includes('--shots')) shots.set(name, await page.screenshot({ animations: 'disabled' }));
};

try {
  await page.goto(new URL('index.html', output).href);
  await page.locator('.tier-form').waitFor();
  assert.equal(await page.locator('.unit-tab-group').count(), 3);
  assert.equal(await page.locator('.unit-records button').count(), 2);
  assert.equal(await map.locator('[data-floor]').count(), 50);
  assert.equal(await map.locator('[data-floor][data-fixed]').count(), 3);
  assert.equal(await map.locator('[data-state="gap"]').count(), 30);
  assert.equal(await page.locator('.contrast-panel tr').count(), 26);
  assert.equal(await page.locator('.contrast-panel .fail').count(), 0);
  await page.locator('#contrast-summary').click();
  assert(await page.locator('.contrast-panel table').isVisible());
  await page.locator('#contrast-summary').click();
  await shot('1280-tier-a.png');

  for (const [key, value, restored] of [
    ['floor_min', '0', '1'], ['floor_max', '51', '10'], ['hp_multiplier', '0', '1'],
    ['event_weights.normal', '-1', '40'], ['encounters.normal.0.weight', '1.5', '30'],
  ]) {
    await field(key).fill(value);
    assert.equal(await field(key).evaluate(input => input.validity.valid), false, key);
    await field(key).fill(restored);
  }
  await field('encounters.normal.0.weight').fill('40');
  assert.equal(await normal.locator('[data-share]').first().textContent(), '50%');
  await field('event_weights.normal').fill('60');
  assert.equal(await page.locator('[data-event-share="normal"]').textContent(), '60%');
  await field('floor_max').fill('12');
  assert.equal(await map.locator('[data-state="overlap"]').count(), 2);
  await switchTo('encounters', 'b');
  assert(await normal.locator('.encounter-card').first().isVisible());
  assert.equal(await field('encounters.normal.0.weight').inputValue(), '40');
  await field('encounters.normal.0.formation_id').selectOption('F-004');
  assert.match(await normal.locator('.encounter-card').first().textContent(), /金級/);
  await button('通常の行を追加').click();
  assert.equal(await normal.locator('.encounter-card').count(), 5);
  await normal.getByRole('button', { name: '外す', exact: true }).last().click();
  await switchTo('events', 'b');
  assert.equal(await page.locator('.event-strip [data-event-share]').count(), 5);
  await switchTo('map', 'b');
  assert.equal(await page.locator('.tier-form .floor-map [data-floor][data-active]').count(), 12);
  await field('encounters.normal.0.formation_id').selectOption('F-001');
  await field('encounters.normal.0.weight').fill('30');
  await field('event_weights.normal').fill('40');
  await field('floor_max').fill('10');
  await page.locator('[data-select="HT-02"]').click();
  await page.locator('[data-select="HT-01"]').click();
  await shot('1280-tier-b.png');

  for (const key of ['normal', 'elite', 'chest', 'miasma', 'camp']) await field(`event_weights.${key}`).fill('0');
  assert.deepEqual(await page.locator('.event-strip [data-empty]').allTextContents(), Array(5).fill('—'));
  for (const [key, value] of Object.entries({ normal: 40, elite: 10, chest: 15, miasma: 10, camp: 5 })) {
    await field(`event_weights.${key}`).fill(String(value));
  }
  await field('floor_max').fill('12');
  await button('保存').click();
  await page.locator('[data-tab="fixed_floor"]').click();
  assert.equal(await page.locator('.unit-records button').count(), 3);
  assert.equal(await map.count(), 0);
  assert.equal(await field('formation_id').count(), 1);
  assert.equal(await field('stage_id').count(), 1);
  await field('type').selectOption('town');
  assert.equal(await field('formation_id').count(), 0);
  assert.equal(await field('stage_id').count(), 0);
  await field('type').selectOption('boss');
  assert(await field('stage_id').inputValue());
  await page.locator('[data-select="HF-03"]').click();
  assert.equal(await field('type').inputValue(), 'camp');
  await page.locator('[data-select="HF-01"]').click();
  await switchTo('map', 'a');
  await shot('1280-fixed.png');

  await page.locator('[data-tab="tier"]').click();
  assert.equal(await field('floor_max').inputValue(), '12');
  await page.setViewportSize({ width: 680, height: 1240 });
  await shot('680-tier.png');
  const save = await button('保存').boundingBox();
  const dock = await page.locator('.prototype-dock').boundingBox();
  assert(save.y + save.height <= dock.y, 'Save button behind comparison controls');
  assert.deepEqual(errors, []);
  if (shots.size) {
    for (const name of await readdir(output)) {
      if (/^(1280|680)-[\w-]+\.png$/.test(name) && !shots.has(name)) await unlink(new URL(name, output));
    }
    for (const [name, data] of shots) await writeFile(new URL(name, output), data);
  }
  console.log(`OK: interaction, contrast, widths${shots.size ? `, ${shots.size} screenshots` : ''}`);
} finally {
  await browser.close();
}
