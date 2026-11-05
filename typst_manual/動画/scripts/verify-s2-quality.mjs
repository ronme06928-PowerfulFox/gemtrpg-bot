// 見出し非表示の実デッキと、隠した長すぎる見出しの負例でR-titleを検証する。
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const main = process.argv.includes('--main');
const deck = path.join(video, main ? '01_1ラウンドの流れ' : '_local/s2-storyboard');
const engine = process.argv.slice(2).find((arg) => !arg.startsWith('--')) || 'C:/Users/yharu/tools/egatari-studio-0.6.3';
function check(src, expectedCode, name) {
  const r = spawnSync(process.execPath, [path.join(engine, 'kit/check.mjs'), src, '--json'], { encoding: 'utf8', maxBuffer: 5 * 1024 * 1024 });
  assert.ifError(r.error);
  const data = JSON.parse(r.stdout);
  fs.writeFileSync(path.join(deck, 'out', name + '.json'), JSON.stringify(data, null, 2) + '\n');
  assert.equal(r.status, expectedCode, r.stderr);
  return data;
}
const normal = check(path.join(deck, 'deck.html'), 0, 'quality-hidden-title');
assert.equal(normal.counts.error, 0);
assert.equal(normal.counts.warn, main ? 29 : 0);
if (main) {
  const warnings = normal.results.filter((r) => r.sev === 'warn');
  assert.equal(warnings.filter((r) => r.code === 'narrMissing').length, 21); // 入場・演出・クレジットのフェードと最後の5秒
  assert.equal(warnings.filter((r) => r.code === 'textContrast').length, 8); // 盤面の既存の白字FP／オレンジ地
}
const negative = path.join(deck, `title-negative-${process.pid}.html`);
assert.ok(!fs.existsSync(negative), '負例の一時原稿を上書きしない');
try {
  fs.writeFileSync(negative, fs.readFileSync(path.join(deck, 'deck.html'), 'utf8').replace('<h2>題と開始状態</h2>', `<h2>${'長い見出し'.repeat(8)}</h2>`));
  const rejected = check(negative, 1, 'quality-title-negative');
  assert.ok(rejected.results.some((r) => r.code === 'titleLong' && r.rule === 'R-title'));
} finally { fs.unlinkSync(negative); }
console.log(`Hidden headings: 0 errors, ${normal.counts.warn} warnings; hidden long heading still fails R-title`);
