import assert from 'node:assert/strict';

export const peak = (samples) => samples.reduce((p, x) => Math.max(p, Math.abs(x)), 0);

export function encodeWav(samples, rate) {
  assert.ok(peak(samples) < 1, '合成音声がクリップする');
  const data = Buffer.alloc(samples.length * 2);
  samples.forEach((v, i) => data.writeInt16LE(Math.round(v * 32767), i * 2));
  const h = Buffer.alloc(44);
  h.write('RIFF'); h.writeUInt32LE(data.length + 36, 4); h.write('WAVEfmt ', 8);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32);
  h.writeUInt16LE(16, 34); h.write('data', 36); h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}

export function decodeWav(data) {
  assert.equal(data.toString('ascii', 0, 4), 'RIFF');
  assert.equal(data.toString('ascii', 8, 12), 'WAVE');
  let format;
  let pcm;
  for (let at = 12; at + 8 <= data.length;) {
    const id = data.toString('ascii', at, at + 4);
    const size = data.readUInt32LE(at + 4);
    assert.ok(at + 8 + size <= data.length, '壊れたWAV');
    if (id === 'fmt ') format = { type: data.readUInt16LE(at + 8), channels: data.readUInt16LE(at + 10), rate: data.readUInt32LE(at + 12), bits: data.readUInt16LE(at + 22) };
    if (id === 'data') pcm = data.subarray(at + 8, at + 8 + size);
    at += 8 + size + size % 2;
  }
  assert.ok(format && pcm, 'WAVに音声がない');
  assert.ok(format.type === 1 && format.channels === 1 && format.bits === 16, 'モノラルPCM16を指定する');
  return { rate: format.rate, samples: Float32Array.from({ length: pcm.length / 2 }, (_, i) => pcm.readInt16LE(i * 2) / 32767) };
}

export function joinParts(parts, rate, gap) {
  let at = 0;
  const cues = [];
  const pieces = [];
  parts.forEach((p, i) => {
    if (p) { pieces.push({ at, samples: p }); at += p.length; }
    if (i < parts.length - 1) {
      cues.push(at / rate);
      if (p && parts.slice(i + 1).some(Boolean)) at += Math.round(gap * rate);
    }
  });
  const samples = new Float32Array(at);
  pieces.forEach((p) => samples.set(p.samples, p.at));
  return { samples, cues };
}

export function mixEffect(target, sound, start) {
  assert.ok(start >= 0 && start + sound.length <= target.length, '効果音が段階外にはみ出す');
  sound.forEach((x, i) => { target[start + i] += x; });
}
