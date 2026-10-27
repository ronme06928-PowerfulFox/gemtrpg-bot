import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
const base = 'typst_manual/動画/01_1ラウンドの流れ/';
const speech = (s) => s.replace(/^##.*$/gm, '').replace(/\[\d+\]/g, '').replace(/\{(?:mark:[^}]+|cue)\}/g, '').replace(/\s/g, '');
test('最新のスロット説明と追加2文以外の語りを保持する', () => {
  const added = 'FPは、スキルの使用コストとして使います。貯めたFPの使い方は、別の回で見ていきます。';
  const current = speech(fs.readFileSync(base + 'narration.md', 'utf8'));
  assert.ok(current.endsWith(added));
  const slots = 'キャラクターは、自身が持つスロットの数だけ1ラウンドの間にスキルを使用できます。今回はお互い、1つずつスロットを持っています。';
  assert.ok(current.includes(slots));
  const original = current.slice(0, -added.length).replace(slots, 'スロットは1回分の行動枠です。今回は2人とも、1つずつスロットを持ちます。');
  assert.equal(createHash('sha256').update(original).digest('hex'), 'e1d6a05edc6bae04c75ef8d70e07d9cfb23bd9586a8abafec12aa46894769594');
});
