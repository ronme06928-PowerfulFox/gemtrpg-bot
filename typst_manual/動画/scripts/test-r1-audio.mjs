import test from 'node:test';
import assert from 'node:assert/strict';
import { encodeWav, decodeWav, joinParts, mixEffect, peak } from './r1-audio.mjs';

test('WAVをヘッダー込みで復元し、音量を保つ', () => {
  const input = Float32Array.of(0, 0.25, -0.5, 0.1);
  const output = decodeWav(encodeWav(input, 24000));
  assert.equal(output.rate, 24000);
  assert.equal(output.samples.length, input.length);
  input.forEach((x, i) => assert.ok(Math.abs(x - output.samples[i]) < 1 / 32767));
});

test('読み上げの区切りからmarkの秒数を求め、空の末尾を音声にしない', () => {
  const p = joinParts([new Float32Array(24000), new Float32Array(12000), null], 24000, 0.1);
  assert.deepEqual(p.cues, [1, 1.6]);
  assert.equal(p.samples.length, 38400);
});

test('効果音を指定位置に混ぜ、声と重なったピークを検査する', () => {
  const voice = new Float32Array(10).fill(0.1);
  mixEffect(voice, Float32Array.of(0.2, -0.2), 4);
  assert.ok(Math.abs(peak(voice) - 0.3) < 1e-6);
  assert.equal(voice[0], voice[8]);
  assert.throws(() => mixEffect(voice, new Float32Array(5), 9), /段階/);
  assert.throws(() => encodeWav(Float32Array.of(1.1), 24000), /クリップ/);
});
