import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('R0: gemuriaは旧版の強調色と控えめな文字色を保持する', () => {
  const css = fs.readFileSync('typst_manual/動画/01_1ラウンドの流れ/themes/gemuria/tokens.css', 'utf8');
  assert.match(css, /--emph-hue:\s*27\s*;/);
  assert.match(css, /--muted:\s*#6e6e6e\s*;/i);
});
