import test from 'node:test';
import assert from 'node:assert/strict';
import { renderCredits } from '../common/credits.mjs';

const branding = { project: 'ジェムリアTRPG', publisher: '創作ゆる大地' };

test('動画ごとのタイトルと使った素材を反映し、別動画にも使える', () => {
  const html = renderCredits(branding, { title: '防御と回避', credits: [{ label: '音声', value: 'VOICEVOX:冥鳴ひまり' }] });
  assert.ok(html.includes('防御と回避') && html.includes('創作ゆる大地'));
  assert.ok(html.includes('VOICEVOX:冥鳴ひまり'));
  assert.ok(!html.includes('1ラウンドの流れ') && !html.includes('Kenney'));
});

test('設定内の記号を文字として表示し、空のタイトルを拒否する', () => {
  const html = renderCredits(branding, { title: 'A&B <例>', credits: [] });
  assert.ok(html.includes('A&amp;B &lt;例&gt;'));
  assert.throws(() => renderCredits(branding, { title: ' ', credits: [] }), /title/);
});
