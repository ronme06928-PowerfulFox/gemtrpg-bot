import test from 'node:test';
import assert from 'node:assert/strict';
import { openingSeconds, openingSound, renderOpening } from '../common/opening.mjs';
import { decodeWav, peak } from './r1-audio.mjs';
test('冒頭は2.6秒の同じチャイムを再生成でき、前後に余裕がある', () => {
  const bytes = openingSound();
  assert.deepEqual(bytes, openingSound());
  const { rate, samples } = decodeWav(bytes);
  assert.equal(samples.length / rate, openingSeconds);
  assert.ok(Math.abs(20 * Math.log10(peak(samples)) + 16) < .01);
  assert.equal(peak(samples.subarray(0, rate * .07)), 0);
  assert.equal(peak(samples.subarray(rate * 1.2)), 0);
});
test('タイトルを文字として配置し、共通ロゴをそのまま参照する', () => {
  const html = renderOpening('<題名>');
  assert.ok(html.includes('&lt;題名&gt;'));
  assert.ok(html.includes('src="images/gemuria_logo.png"'));
});
