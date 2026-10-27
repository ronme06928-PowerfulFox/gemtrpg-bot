import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
const base = 'typst_manual/動画/01_1ラウンドの流れ/';
const speech = (s) => s.replace(/^##.*$/gm, '').replace(/\[\d+\]/g, '').replace(/\{(?:mark:[^}]+|cue)\}/g, '').replace(/\s/g, '');
test('承認された語りの変更以外は元の合意文を保持する', () => {
  const added = 'FPは、スキルの使用コストとして使います。貯めたFPの使い方は、別の回で見ていきます。';
  const current = speech(fs.readFileSync(base + 'narration.md', 'utf8'));
  assert.ok(current.endsWith(added));
  const slots = 'キャラクターは、自身が持つスロットの数だけ1ラウンドの間にスキルを使用できます。今回はお互い、1つずつスロットを持っています。';
  assert.ok(current.includes(slots));
  const original = current.slice(0, -added.length)
    .replace('今回は、戦闘における1ラウンドの流れを紹介します。', '1ラウンドの流れを見ていきます。')
    .replace('今回は味方と敵が1回ずつ、基本スキルを使用します。', '今回は、味方と敵が1回ずつ行動し、「基本の一太刀」を使います。')
    .replace('駒の上の丸がスロットです。', '')
    .replace('スロットの中に速度値が表示されます。', '駒の上の丸がスロットです。中に速度値が表示されます。')
    .replace('味方の速度値は6、敵の速度値は4です。', '味方は出目4に速度補正2を足して、速度値6です。敵は出目3に速度補正1を足して、速度値4です。')
    .replace('味方の最終威力は9です。', '味方の出目は2と3です。最終威力は9です。')
    .replace('敵の最終威力は6です。', '敵の出目は1と1です。最終威力は6です。')
    .replace('スキルの最終威力である9', '威力9')
    .replace(slots, 'スロットは1回分の行動枠です。今回は2人とも、1つずつスロットを持ちます。');
  assert.equal(createHash('sha256').update(original).digest('hex'), 'e1d6a05edc6bae04c75ef8d70e07d9cfb23bd9586a8abafec12aa46894769594');
});
test('タイトルの紹介文と、結果だけの語りへ整理する', () => {
  const s = speech(fs.readFileSync(base + 'narration.md', 'utf8'));
  assert.ok(s.startsWith('今回は、戦闘における1ラウンドの流れを紹介します。'));
  assert.ok(s.indexOf('駒の上の丸がスロットです。') < s.indexOf('各スロットで'));
  assert.ok(s.includes('味方の速度値は6、敵の速度値は4です。'));
  assert.ok(!/出目は|出目[1-6]/.test(s));
  assert.ok(s.includes('スキルの最終威力である9'));
});
test('字幕の括弧は残し、音声の読みからだけ外す', () => {
  const config = JSON.parse(fs.readFileSync(base + 'voice/config.json', 'utf8'));
  let text = '「基本の一太刀」の効果と「ラウンド終了時」に';
  for (const [display, reading] of Object.entries(config.readings)) text = text.replaceAll(display, reading);
  assert.equal(text, 'きほんのひとたちの効果とラウンド終了時に');
});
