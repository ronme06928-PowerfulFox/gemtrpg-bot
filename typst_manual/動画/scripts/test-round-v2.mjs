import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
const base = 'typst_manual/動画/01_1ラウンドの流れ/';
const speech = (s) => s.replace(/^##.*$/gm, '').replace(/\[\d+\]/g, '').replace(/\{(?:mark:[^}]+|cue)\}/g, '').replace(/\s/g, '');
test('合意済みの語りを変えず承認2文だけ加える', () => {
  const added = 'FPは、スキルの使用コストとして使います。貯めたFPの使い方は、別の回で見ていきます。';
  const current = speech(fs.readFileSync(base + 'narration.md', 'utf8'));
  assert.ok(current.endsWith(added));
  // 承認前原稿（0f96e35）の全語り。浅いcheckoutでも検査できる。
  assert.equal(createHash('sha256').update(current.slice(0, -added.length)).digest('hex'), 'e1d6a05edc6bae04c75ef8d70e07d9cfb23bd9586a8abafec12aa46894769594');
});
