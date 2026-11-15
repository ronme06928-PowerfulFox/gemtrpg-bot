import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const driver = execFileSync('python', [
  '-c', "from pathlib import Path; import playwright; print(Path(playwright.__file__).parent / 'driver' / 'package')",
], { encoding: 'utf8' }).trim();
const { chromium } = createRequire(import.meta.url)(driver);
const output = new URL('../../_local/ui_layout_proto/', import.meta.url);
const preview = new URL('index.html', output);
const action = (page, name) => page.getByRole('button', { name, exact: true });

async function fit(page, palette) {
  await page.getByLabel('配色', { exact: true }).selectOption(palette);
  const overflow = await page.locator('html, .workspace, .workspace-head, .panel-scroll, .workspace-footer, .menu-grid, #comparison-controls')
    .evaluateAll(nodes => nodes.filter(node => node.scrollWidth > node.clientWidth + 1).map(node => node.className || node.id));
  assert.deepEqual(overflow, []);
  const clippedRows = await page.locator('.record').evaluateAll(rows =>
    rows.filter(row => row.scrollHeight > row.clientHeight + 1).map(row => row.dataset.record));
  assert.deepEqual(clippedRows, []);
  const contrast = await page.evaluate(() => {
    const rgb = color => color.match(/[\d.]+/g)?.map(Number);
    const luminance = color => color.slice(0, 3).map(value => {
      const channel = value / 255;
      return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
    }).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
    const ratio = (color, paper) => {
      const values = [luminance(color), luminance(paper)].sort((a, b) => b - a);
      return (values[0] + .05) / (values[1] + .05);
    };
    const background = node => {
      const value = node && rgb(getComputedStyle(node).backgroundColor);
      return !node ? [255, 255, 255] : value && value[3] !== 0 ? value : background(node.parentElement);
    };
    const findings = [];
    for (const node of document.querySelectorAll('main *, #comparison-controls *')) {
      if (!node.getClientRects().length || node.closest('button:disabled, input:disabled, select:disabled')) continue;
      const style = getComputedStyle(node);
      const hasText = [...node.childNodes].some(child => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
      if (hasText || node.matches('select, input:not([type="checkbox"]), textarea')) {
        const value = ratio(rgb(style.color), background(node));
        if (value < 4.5) findings.push([node.className || node.tagName, 'text', value]);
      }
      if (node.matches('button, input, select, textarea')) {
        const value = ratio(rgb(style.borderTopColor), background(node.parentElement));
        if (value < 3) findings.push([node.className || node.tagName, 'border', value]);
      }
    }
    return findings.slice(0, 15);
  });
  assert.deepEqual(contrast, [], palette);
}

async function exercise(page, capture) {
  await page.goto(preview.href);
  const show = name => action(page, name).click();
  const query = page.getByRole('searchbox');
  await page.getByRole('heading', { name: 'メインメニュー' }).waitFor();
  assert.equal(await page.getByLabel('配色', { exact: true }).inputValue(), 'a');
  assert(await action(page, 'ダンジョン').isDisabled());
  assert(await page.getByRole('navigation', { name: 'データ管理' }).getByRole('button', { name: 'ユニット管理' }).isVisible());
  await show('アカウント');
  await page.getByRole('heading', { name: 'アカウント' }).waitFor();
  await show('メインメニュー');
  for (const palette of ['a', 'b']) {
    await fit(page, palette);
    if (capture) capture.push(await page.screenshot());
  }
  await show('ユニット管理');
  await query.fill('U-');
  const row = page.locator('#records [data-record]').last();
  await row.scrollIntoViewIfNeeded();
  const position = await page.locator('#records').evaluate(el => el.scrollTop);
  assert(position > 0);
  await row.click();
  const name = page.getByLabel('名称', { exact: true });
  await name.fill('試作・ユニット');
  await show('一覧に戻る');
  await show('入力を保持して戻る');
  assert.equal(await query.inputValue(), 'U-');
  assert.equal(await page.locator('#records').evaluate(el => el.scrollTop), position);
  await row.click();
  assert.equal(await name.inputValue(), '試作・ユニット');
  for (const [density, palette] of [['13', 'a'], ['13', 'b'], ['16', 'a']]) {
    await page.getByLabel('文字サイズ').selectOption(density);
    assert.equal(await name.inputValue(), '試作・ユニット');
    await fit(page, palette);
    if (capture) capture.push(await page.screenshot());
  }
  await show('メインメニュー');
  await show('入力を保持して移動');
  await show('マスターデータ');
  await show('承認待ち');
  await query.fill('P');
  const first = page.locator('#records [data-record]').first();
  const oldId = await first.getAttribute('data-record');
  await first.click();
  assert.equal(await page.locator('.diff').count(), 5);
  await fit(page, 'b');
  await show('承認して公開');
  await show('公開');
  assert.equal(await query.inputValue(), 'P');
  assert.equal(await page.locator('[data-record="' + oldId + '"]').count(), 0);
  await first.click();
  await page.locator('.diff').first().waitFor();
  await show('メインメニュー');
  await show('マスターデータ');
  if (await action(page, '一覧に戻る').count()) await show('一覧に戻る');
  await show('公開データ');
  for (const palette of ['a', 'b']) {
    await fit(page, palette);
    if (capture) capture.push(await page.screenshot());
  }
  await show('メインメニュー');
  await show('セッション');
  assert(await page.getByRole('heading', { name: 'ルーム一覧' }).isVisible());
  await show('メインメニュー');
  const role = page.getByLabel('閲覧者');
  for (const viewer of ['gm', 'public']) {
    await role.selectOption(viewer);
    assert.equal(await action(page, '承認待ち').count(), 0);
    await show('ユニット管理');
    if (await action(page, '一覧に戻る').count()) await show('一覧に戻る');
    await query.fill('U-');
    assert.equal(await page.getByText('制作者・GMのみ', { exact: true }).count(), 0);
    await page.locator('#records [data-record]').first().click();
    assert.equal(await name.count(), 0);
    await show('メインメニュー');
    await show('マスターデータ');
    assert.equal(await action(page, '承認待ち').count(), 0);
    await show('メインメニュー');
  }
  await role.selectOption('author');
  await page.getByLabel('アプリ管理者').uncheck();
  assert.equal(await action(page, '承認待ち').count(), 0);
  await show('マスターデータ');
  await query.fill('Mp-03');
  await page.locator('#records [data-record]').first().click();
  await show('下書きを作成');
  await page.getByLabel('効果・説明', { exact: true }).fill('提案の本文');
  await show('下書きを保存');
  assert.equal(await action(page, '承認して公開').count(), 0);
}

const browser = await chromium.launch({ channel: 'chrome', timeout: 10000 });
const images = [];
try {
  for (const [width, height] of [[1280, 800], [1920, 1080], [680, 800]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    page.setDefaultTimeout(5000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await exercise(page, width === 1280 ? images : null);
    assert.deepEqual(errors, []);
    await page.close();
    console.log(width + 'px: メニュー・管理・承認・ロール OK');
  }
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  await page.setContent('<style>body{margin:0;display:grid;align-content:start;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;background:#7b8798}</style><body>' +
    images.map(img => '<img alt="" style="width:100%;display:block" src="data:image/png;base64,' + img.toString('base64') + '">').join(''));
  await page.screenshot({ path: fileURLToPath(new URL('comparison.png', output)), fullPage: true });
} finally {
  await browser.close();
}
