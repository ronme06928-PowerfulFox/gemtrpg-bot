// .claude/launch.json の gemtrpg（127.0.0.1:5000）に限定した表示比較。
// 新規のテストユーザーだけを使い、既存ルーム・ログを取得しない。
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath, pathToFileURL } from 'node:url';

const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(video, '_local/s1-components/out');
const engine = process.argv[2] || 'C:/Users/yharu/tools/egatari-studio';
const wsgi = process.argv.includes('--wsgi');
let bridge;
let pending = Promise.resolve();
let ask;
if (wsgi) {
  const launch = JSON.parse(fs.readFileSync(path.join(video, '../../.claude/launch.json'), 'utf8')).configurations.find((c) => c.name === 'gemtrpg');
  assert.deepEqual(launch.runtimeArgs, ['app.py']);
  bridge = spawn(launch.runtimeExecutable, ['-u', path.join(video, 'scripts/s1-local-wsgi.py')], {
    cwd: path.resolve(video, '../..'), env: { ...process.env, PYTHONUTF8: '1' }, stdio: ['pipe', 'pipe', 'pipe']
  });
  const lines = createInterface({ input: bridge.stdout });
  const queue = [];
  bridge.on('error', (e) => queue.splice(0).forEach((q) => q.reject(e)));
  bridge.stderr.resume();
  bridge.on('exit', (code) => queue.splice(0).forEach((q) => q.reject(new Error(`WSGI bridge exited: ${code}`))));
  lines.on('line', (line) => queue.shift()?.resolve(JSON.parse(line)));
  ask = (request) => {
    const answer = pending.then(() => new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('WSGI request timeout')), 15000);
      queue.push({ resolve: (r) => { clearTimeout(timer); resolve(r); }, reject: (e) => { clearTimeout(timer); reject(e); } });
      bridge.stdin.write(JSON.stringify(request) + '\n');
    }));
    pending = answer.then(() => undefined);
    return answer;
  };
}
const { launch } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const browser = await launch();
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await context.newPage();
  // ローカル以外への要求を遮断する。認証状態を引き継がない専用コンテキスト。
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url());
    if (['data:', 'blob:'].includes(u.protocol)) return route.continue();
    if (u.origin !== 'http://127.0.0.1:5000' || u.pathname.startsWith('/socket.io')) return route.abort();
    if (!wsgi) return route.continue();
    const result = await ask({ path: u.pathname + u.search, method: route.request().method(), body: route.request().postData(), mime: route.request().headers()['content-type'] });
    return route.fulfill({ status: result.status, contentType: result.mime, body: Buffer.from(result.body, 'base64') });
  });
  await page.goto('http://127.0.0.1:5000/');
  const status = await page.evaluate(async (data) => (await fetch('/api/register', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
  })).status, { login_name: `video-s1-test-${randomUUID()}`, display_name: '動画S1格子テスト', password: randomUUID() });
  assert.equal(status, 201, '専用テストアカウント');
  // 復旧コード等を含むレスポンス本文は記録しない。
  await page.waitForFunction(() => typeof window.renderVisualMap === 'function');
  // アプリの既存盤面HTMLを使い、表示用データだけをブラウザメモリに注入する。
  // サーバーのルーム作成・参加・チャット・保存イベントは使わない。
  await page.evaluate(async () => {
    if (typeof socket !== 'undefined' && socket) socket.disconnect();
    const html = await (await fetch('/4_visual_battle.html')).text();
    document.body.innerHTML = html;
    const container = document.getElementById('visual-battle-container');
    Object.assign(container.style, { display: 'block', position: 'fixed', inset: '0' });
    const viewport = document.getElementById('map-viewport');
    Object.assign(viewport.style, { display: 'block', position: 'absolute', inset: '0', width: '1280px', height: '720px' });
    window.visualScale = 1;
    window.visualOffsetX = 70;
    window.visualOffsetY = -760;
    window.visualViewNeedsCenter = false;
    const testState = { characters: [], battle_map_data: {} };
    window.BoardPresentationCoordinator = { state: testState };
    window.BattleStore = { state: testState };
    window.renderVisualMap();
  });
  const style = () => page.locator('#game-map').evaluate((el) => {
    const s = getComputedStyle(el);
    return { backgroundImage: s.backgroundImage.startsWith('url(') ? 'url(ruins-battle.png)' : s.backgroundImage,
      backgroundSize: s.backgroundSize, backgroundRepeat: s.backgroundRepeat, backgroundPosition: s.backgroundPosition };
  });
  const before = await style();
  await page.screenshot({ path: path.join(out, 'app-grid-before.png') });
  const png = fs.readFileSync(path.join(video, 'common/assets/ruins-battle.png')).toString('base64');
  await page.evaluate(async (png) => {
    const src = `data:image/png;base64,${png}`;
    const img = new Image(); img.src = src; await img.decode();
    window.BattleStore.state.battle_map_data.background_image = src;
    window.renderVisualMap();
  }, png);
  const withImage = await style();
  await page.screenshot({ path: path.join(out, 'app-grid-background.png') });
  assert.ok(before.backgroundImage.includes('linear-gradient'));
  assert.equal(withImage.backgroundImage, 'url(ruins-battle.png)');
  assert.equal(withImage.backgroundSize, 'contain');
  assert.equal(withImage.backgroundRepeat, 'no-repeat');
  await page.evaluate(() => { window.BattleStore.state.battle_map_data.background_image = ''; window.renderVisualMap(); });
  const removed = await style();
  await page.screenshot({ path: path.join(out, 'app-grid-removed.png') });
  fs.writeFileSync(path.join(out, 'grid-report.json'), JSON.stringify({
    source: '.claude/launch.json:gemtrpg', origin: 'http://127.0.0.1:5000',
    transport: wsgi ? 'TCP接続失敗のため、同じPython環境・app.pyのFlask test_clientで実ルートを処理' : 'TCP',
    account: '新規の動画S1格子テスト（復旧情報・識別子を保存しない）',
    method: '実アプリのHTML・CSS・renderVisualMapにブラウザ内テストデータを渡す。ルーム・チャット・Socket保存なし。',
    before, withImage, removed
  }, null, 2) + '\n');
  console.log('Local app grid: image replaces gradients; contain, no-repeat, center');
} finally { await browser.close(); bridge?.kill(); }
