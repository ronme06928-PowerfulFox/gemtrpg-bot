import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const driver = execFileSync('python', ['-c', "from pathlib import Path; import playwright; print(Path(playwright.__file__).parent / 'driver' / 'package')"], { encoding: 'utf8' }).trim();
const { chromium } = createRequire(import.meta.url)(driver);
const output = new URL('../../_local/encyclopedia_proto/', import.meta.url);
const shots = new URL('verification/', output);
const takeShots = process.argv.includes('--shots');
if (takeShots) await mkdir(shots, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => { if (/^https?:/.test(request.url())) errors.push(request.url()); });
const open = prefix => page.locator(`button[data-book="${prefix}"]`).click();
const button = name => page.getByRole('button', { name, exact: true });
const enter = key => page.locator(`button[data-door="${key}"]`).click();
const row = id => page.locator(`button[data-entry="${id}"]`);
const current = () => page.locator('.specimen-id').textContent();
const minimum = { body: Infinity, text: Infinity, frame: Infinity };

async function capture(role, scene, photograph = false) {
  const result = await page.evaluate(() => {
    const channels = color => color.match(/[\d.]+/g).map(Number);
    const luminance = color => color.slice(0, 3).map(value => {
      const x = value / 255;
      return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4;
    }).reduce((sum, x, index) => sum + x * [.2126, .7152, .0722][index], 0);
    const ratio = (a, b) => (Math.max(luminance(a), luminance(b)) + .05) / (Math.min(luminance(a), luminance(b)) + .05);
    function background(node) {
      const color = channels(getComputedStyle(node).backgroundColor);
      return color[3] === 0 ? background(node.parentElement) : color;
    }
    const minimum = { body: Infinity, text: Infinity, frame: Infinity };
    const failures = [];
    for (const node of document.querySelectorAll('header *, main *, dialog *')) {
      if (!node.getClientRects().length || node instanceof SVGElement) continue;
      const style = getComputedStyle(node);
      const text = [...node.childNodes].some(child => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
      if ((text || node.matches('input, select')) && !node.closest('button:disabled:not(.locked)')) {
        const contrast = ratio(channels(style.color), background(node));
        const kind = node.closest('.book-reading-body') ? 'body' : 'text';
        minimum[kind] = Math.min(contrast, minimum[kind]);
        if (contrast < 4.5) failures.push(['text', node.className, node.textContent.trim().slice(0, 24), contrast]);
      }
      if (node.matches('button:not(:disabled), input, select, summary, .locked, .clasp, .clasp-hole, #doors, .door, .door-emblem, .door-lock, #shelves, .shelf-header, .open-book, .specimen-tags li, #page-jump-form')) {
        const contrast = ratio(channels(style.borderTopColor), background(node.parentElement));
        minimum.frame = Math.min(contrast, minimum.frame);
        if (contrast < 3) failures.push(['border', node.className, contrast]);
      }
    }
    return { minimum, failures };
  });
  assert.deepEqual(result.failures.slice(0, 12), [], `${role} ${scene}`);
  for (const key of Object.keys(minimum)) minimum[key] = Math.min(minimum[key], result.minimum[key] ?? Infinity);
  if (takeShots && photograph) {
    await page.mouse.move(20, 75);
    await page.screenshot({ path: fileURLToPath(new URL(`${role}-${scene}.png`, shots)), animations: 'disabled' });
  }
}

async function turnPaused(expected) {
  const turn = await page.locator('.turn-leaf').evaluate(async leaf => {
    const animation = leaf.getAnimations()[0];
    const motions = leaf.parentElement.getAnimations({ subtree: true })
      .filter(motion => motion === animation || motion.animationName === 'page-shade');
    for (const motion of motions) motion.pause();
    await Promise.all(motions.map(motion => motion.ready));
    const corners = [];
    leaf.inert = false;
    try {
      for (const time of [100, 200, 300, 410]) {
        animation.currentTime = time;
        const matrix = new DOMMatrix(getComputedStyle(leaf).transform);
        const face = leaf.querySelector(matrix.m11 > 0 ? '.turn-front' : '.turn-back');
        for (const [block, inline] of [['top', 'left'], ['top', 'right'], ['bottom', 'left'], ['bottom', 'right']]) {
          const marker = document.createElement('span');
          Object.assign(marker.style, {
            position: 'absolute', [block]: '4px', [inline]: '4px',
            width: '3px', height: '3px', pointerEvents: 'auto', zIndex: '1',
          });
          face.append(marker);
          const bounds = marker.getBoundingClientRect();
          const x = bounds.x + bounds.width / 2;
          const y = bounds.y + bounds.height / 2;
          corners.push({ time, block, inline, visible: document.elementFromPoint(x, y) === marker });
          marker.remove();
        }
      }
    } finally {
      leaf.inert = true;
    }
    for (const motion of motions) motion.currentTime = 310;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const matrix = new DOMMatrix(getComputedStyle(leaf).transform);
    return {
      duration: animation.effect.getTiming().duration,
      width: leaf.offsetWidth,
      spreadWidth: document.querySelector('#spread').offsetWidth,
      angle: Math.acos(matrix.m11) * 180 / Math.PI,
      back: leaf.querySelector('.turn-back .specimen-id')?.textContent,
      front: !!leaf.querySelector('.turn-front .skill-detail-command'),
      corners,
    };
  });
  assert(turn.duration >= 400 && turn.duration <= 600);
  assert(Math.abs(turn.width * 2 - turn.spreadWidth) <= 1);
  assert(turn.angle > 90 && turn.angle < 135);
  assert.equal(turn.back, expected);
  assert.equal(turn.front, true);
  assert.deepEqual(turn.corners.filter(corner => !corner.visible), []);
}

const finishTurn = () => page.waitForFunction(() => !document.querySelector('.turn-leaf').dataset.direction);

try {
  for (const role of ['player', 'gm']) {
    await page.goto(new URL('index.html', output).href);
    await page.getByLabel('見る人', { exact: true }).selectOption(role);
    assert.equal(await page.locator('.shelf-book:visible').count(), 0);
    assert.deepEqual(await page.locator('.door-title').allTextContents(), ['冒険者', '魔物', '世界の理', 'ホロウ']);
    assert(await page.locator('main').evaluate(node => node.getBoundingClientRect().bottom <= innerHeight
      && document.documentElement.scrollHeight === innerHeight));
    const hollow = page.getByRole('img', { name: /ホロウ.*錠/ });
    await hollow.click();
    assert(await page.locator('#doors').isVisible());
    assert.equal(await page.locator('#shelves:visible').count(), 0);
    assert.equal(await hollow.locator('button, a, [tabindex]').count(), 0);
    assert.match(await page.locator('[data-door="monsters"]').innerText(), role === 'gm' ? /48\/48/ : /28\/48/);
    await capture(role, '01-doors', true);

    const dimensions = [];
    const colors = [];
    for (const [key, keys] of [
      ['adventurers', [['Ps', 'Pb', 'Pp'], ['Ms', 'Mb', 'Mp'], ['B', 'C', 'D'], ['radiance', 'item']]],
      ['monsters', [['E', 'enemy', 'passive']]],
      ['world', [['glossary', 'buff']]],
    ]) {
      await enter(key);
      const spines = await page.locator('.shelf-book:visible').evaluateAll(books => books.map(book => {
        const style = getComputedStyle(book);
        return {
          key: book.dataset.book, width: book.offsetWidth, height: book.offsetHeight, top: book.offsetTop,
          colors: ['--jewel', '--jewel-mid', '--jewel-deep'].map(property => style.getPropertyValue(property)),
        };
      }));
      assert.deepEqual(await page.locator('.shelf-row:visible').evaluateAll(rows =>
        rows.map(row => [...row.querySelectorAll('[data-book]')].map(book => book.dataset.book))), keys);
      assert.equal(await page.locator('.shelf-row:visible h3, .shelf-row:visible h2').count(), 0);
      if (key !== 'adventurers') assert(await page.locator('.shelf-prop:visible').count() >= 2);
      assert(await page.locator('main').evaluate(node => node.getBoundingClientRect().bottom <= innerHeight));
      assert.equal(await page.locator('.shelf-prop[aria-hidden="true"]:visible').count(), await page.locator('.shelf-prop:visible').count());
      for (const row of keys.filter(row => row.length)) {
        assert.equal(new Set(spines.filter(book => row.includes(book.key)).map(book => book.top)).size, 1);
      }
      dimensions.push(...spines.map(book => `${book.width}x${book.height}`));
      colors.push(...spines.map(book => book.colors));
      await capture(role, key === 'adventurers' ? '02-adventurers' : key, key === 'adventurers');
      await button('扉へ戻る').click();
    }
    assert.deepEqual([...new Set(dimensions)], ['80x278']);
    for (let channel = 0; channel < 3; channel++) {
      assert.equal(new Set(colors.map(palette => palette[channel])).size, 16);
    }
    assert.match(await page.locator('#total-count').textContent(), role === 'gm' ? /298\/298/ : /278\/298/);
    await enter('adventurers');
    assert.equal(await page.locator('.spine-title').first().evaluate(node => getComputedStyle(node).writingMode), 'vertical-rl');
    await page.locator('.shelf-book').first().hover();
    await page.waitForFunction(() => new DOMMatrix(getComputedStyle(document.querySelector('.shelf-book')).transform).m42 < -6);
    await button('扉へ戻る').click();
    await enter('monsters');
    await open('E');
    assert.equal(await page.locator('#chapter-tabs button').count(), 0);
    assert.equal(await button('前へ').isDisabled(), true);
    assert.equal(await row('E-01').isDisabled(), role === 'player');
    assert.equal(await page.getByText('戦闘で出会うと解禁', { exact: true }).count(), role === 'player' ? 1 : 0);
    assert.equal(await page.locator('#spread .gem-motion').count(), 0);
    await capture(role, 'locked-contents');
    await page.keyboard.press('ArrowRight');
    await finishTurn();
    assert.equal(await page.locator('#page-number').textContent(), '2/38');
    await page.keyboard.press('ArrowRight');
    await finishTurn();
    assert.equal(await current(), 'E-00');
    assert.match(await page.locator('#spread .encounter-date').textContent(), /初めて出会った日\s*2026/);
    await capture(role, 'encounter');
    await button('次へ').click();
    const nextId = role === 'player' ? 'E-02' : 'E-01';
    await turnPaused(nextId);
    await capture(role, 'turn');
    await page.locator('.open-book').evaluate(book => {
      for (const animation of book.getAnimations({ subtree: true })) {
        if (animation.playState === 'paused') animation.play();
      }
    });
    await finishTurn();
    assert.equal(await current(), nextId);
    assert.equal(await page.locator('#page-number').textContent(), role === 'player' ? '5/38' : '4/38');
    await page.locator('#page-number').click();
    await page.getByLabel('移動先のページ').fill('4');
    await button('移動').click();
    if (role === 'player') {
      assert.equal(await current(), 'E-02');
      assert.match(await page.getByRole('alert').textContent(), /解禁/);
      await page.keyboard.press('Escape');
      assert(await page.locator('#book-window').isVisible());
    } else {
      assert.equal(await current(), 'E-01');
    }
    if (role === 'gm') assert.match(await page.locator('.encounter-date').textContent(), /未記録/);
    await page.keyboard.press('ArrowLeft');
    await finishTurn();
    assert.equal(await current(), 'E-00');
    await button('棚へ戻る').click();
    assert.deepEqual(await page.locator('.shelf-book:visible').evaluateAll(books => books.map(book => book.dataset.book)), ['E', 'enemy', 'passive']);
    await button('扉へ戻る').click();
    await enter('adventurers');
    await open('Ps');
    await row('Ps-04').click();
    assert(await page.locator('.skill-detail-command').isVisible());
    assert(await page.getByText('【コスト】', { exact: true }).isVisible());
    assert.match(await page.locator('.specimen-tags').textContent(), /物理/);
    assert.equal(await page.locator('.encounter-date').count(), 0);
    assert.equal(await page.locator('.text-page .skill-detail-tags:visible').count(), 0);
    const heights = await page.locator('#spread > div').evaluateAll(pages => pages.map(page => page.offsetHeight));
    assert.equal(heights[0], heights[1]);
    await capture(role, 'skill');
    await page.locator('a[data-entry="W-00"]').first().click();
    assert.equal(await current(), 'W-00');
    assert(await page.locator('.specimen-page .flavor').isVisible());
    assert.equal(await page.locator('.text-page .flavor').count(), 0);
    assert.equal(await page.getByText('これを使う物', { exact: true }).count(), 0);
    await button('棚へ戻る').click();

    await button('扉へ戻る').click();
    await enter('world');
    assert.equal(await page.locator('[data-book="glossary"] .clasp.complete .gem-motion').count(), 1);
    await open('glossary');
    assert.equal(await page.locator('#page-number').textContent(), '1/91');
    assert.deepEqual(await page.locator('#chapter-tabs button').allTextContents(),
      ['ルール', 'タイミング', '効果', 'バフ', 'デバフ', '状態異常', 'スキルタグ']);
    assert.equal(await page.locator('#chapter-tabs [aria-current]').textContent(), 'ルール');
    assert.deepEqual(await page.locator('.contents-grid').evaluateAll(grids => grids.map(grid => grid.childElementCount)), [12, 12]);
    assert.equal(await row('W-16').locator('small').textContent(), '3ページ');
    const fullCard = await row('W-16').boundingBox();
    await button('次へ').click();
    await finishTurn();
    assert.equal(await page.locator('#page-number').textContent(), '2/91');
    assert.deepEqual(await page.locator('.contents-grid').evaluateAll(grids => grids.map(grid => grid.childElementCount)), [10, 0]);
    for (const [chapter, start] of [
      ['効果', 51], ['バフ', 64], ['デバフ', 72], ['状態異常', 78], ['スキルタグ', 85], ['タイミング', 37],
    ]) {
      await button(chapter).click();
      assert.equal(await page.locator('#page-number').textContent(), `${start}/91`);
      assert.equal(await page.locator('#chapter-tabs [aria-current]').textContent(), chapter);
      assert((await page.locator('.contents h3').innerText()).includes(chapter));
    }
    assert.equal(await page.locator('#chapter-tabs [aria-current]').textContent(), 'タイミング');
    assert.equal(await page.locator('#page-number').textContent(), '37/91');
    assert.match(await page.locator('.contents h3').innerText(), /タイミング/);
    assert.equal(await row('W-24').locator('small').textContent(), '43ページ');
    await capture(role, '03-chapters', true);
    await button('前へ').click();
    await finishTurn();
    assert.equal(await current(), 'W-73');
    assert.equal(await page.locator('#chapter-tabs [aria-current]').textContent(), 'ルール');
    await button('次へ').click();
    await finishTurn();
    await row('W-24').click();
    await button('次へ').click();
    await finishTurn();
    assert.equal(await current(), 'W-25');
    assert.equal(await page.locator('#chapter-tabs [aria-current]').textContent(), 'タイミング');
    await button('目次へ戻る').click();
    assert.equal(await page.locator('#page-number').textContent(), '37/91');
    assert.equal(await page.locator('.contents-entry.highlighted').getAttribute('data-entry'), 'W-25');
    await row('W-24').click();
    assert.match(await page.locator('#page-jump summary').innerText(), /ページ\s+43\/91/);
    await page.locator('#page-number').click();
    await capture(role, 'page-selection');
    await page.getByLabel('移動先のページ').fill('1');
    await button('移動').click();
    assert.equal(await page.locator('#page-number').textContent(), '1/91');
    await button('棚へ戻る').click();

    await button('扉へ戻る').click();
    await enter('adventurers');
    await open('B');
    assert.equal(await row('B-01').count(), 1);
    assert.deepEqual(await page.locator('.contents-grid').evaluateAll(grids => grids.map(grid => grid.childElementCount)), [4, 0]);
    const shortCard = await row('B-01').boundingBox();
    assert.deepEqual([shortCard.width, shortCard.height], [fullCard.width, fullCard.height]);
    await row('B-01').click();
    assert.equal(await page.locator('#book-window.prism .specimen-mount use').getAttribute('href'), '#prism-cut');
    await capture(role, 'blessing');
    await button('棚へ戻る').click();

    await button('扉へ戻る').click();
    const query = page.getByRole('searchbox');
    await query.fill('出血');
    const kinds = await page.locator('#search-results [data-entry]').evaluateAll(rows => [...new Set(rows.map(row => row.dataset.kind))]);
    assert(kinds.includes('glossary') && kinds.includes('skill') && kinds.includes('buff'));
    await query.fill('W-24');
    await row('W-24').click();
    assert.equal(await current(), 'W-24');
    assert.equal(await page.locator('#chapter-tabs [aria-current]').textContent(), 'タイミング');
    await button('棚へ戻る').click();
    await query.fill('Bu-08');
    await row('Bu-08').click();
    assert.equal(await current(), 'Bu-08');
    await capture(role, '06-search');
    assert.equal(await page.locator('html').evaluate(el => el.scrollWidth), 1280);
  }
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(new URL('index.html', output).href);
  await enter('adventurers');
  assert.equal(await page.locator('.clasp .spark').first().evaluate(node => getComputedStyle(node).animationName), 'none');
  const spine = page.locator('.shelf-book').first();
  await spine.hover();
  assert.equal(await spine.evaluate(node => getComputedStyle(node).transform), 'none');
  await open('Ps');
  await button('次へ').click();
  assert.equal(await current(), 'Ps-00');
  assert.equal(await page.locator('.turn-leaf').evaluate(leaf => leaf.getAnimations().length), 0);
  assert.equal(await page.locator('#spread .spark').first().evaluate(node => getComputedStyle(node).animationName), 'none');
  assert.deepEqual(errors, []);
  console.log(`Contrast (min): body ${minimum.body.toFixed(2)}:1, all text ${minimum.text.toFixed(2)}:1, frames ${minimum.frame.toFixed(2)}:1`);
  console.log('Verified 4 doors, 16 equal-sized spines with distinct palettes, chapter navigation, page turns and offline use for player and GM.');
} finally {
  await browser.close();
}
