import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const base = 'typst_manual/動画/01_1ラウンドの流れ/';
const lines = file => fs.readFileSync(base + file, 'utf8').split('\n').filter(s => /^[EN]: /.test(s)).map(s => s.replace(/\{(?:mark:[^}]+|cue)\}/g, ''));
test('承認された掛け合い台本の文字を保持する', () => {
  assert.deepEqual(lines('narration.md'), lines('narration-v3-dialogue.md'));
});
test('題の一文と、結果だけの語りを保持する', () => {
  const s=lines('narration.md').join('');
  assert.ok(s.startsWith('E: 今回は、戦闘の1ラウンドの流れを見ていきましょう。'));
  assert.ok(s.includes('味方の速度値は6、敵の速度値は4です。'));
  assert.ok(!/出目は|出目[1-6]/.test(s));
  assert.ok(s.includes('スキルの最終威力の9が、そのまま敵へのダメージとして与えられます。'));
});
test('字幕の括弧は残し、音声の読みからだけ外す', () => {
  const config = JSON.parse(fs.readFileSync(base + 'voice/config.json', 'utf8'));
  let text = '「基本の一太刀」の効果と「ラウンド終了時」に';
  for (const [display, reading] of Object.entries(config.readings)) text = text.replaceAll(display, reading);
  assert.equal(text, 'きほんのひとたちの効果とラウンド終了時に');
});
