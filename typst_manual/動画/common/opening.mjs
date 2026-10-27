import fs from 'node:fs';
import path from 'node:path';
import { encodeWav, peak } from '../scripts/r1-audio.mjs';

export const openingSeconds = 2.6;
export function renderOpening(title) {
  const text = title.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  return `<div class="video-opening"><img class="opening-logo" src="images/gemuria_logo.png" alt="ジェムリア"><div class="opening-project">ジェムリアTRPG</div><div class="opening-title">${text}</div><div class="opening-rule"></div></div>`;
}

// 外部素材を使わない短い3音チャイム。基準-22dBFS＋採用済み6dB。
export function openingSound() {
  const rate = 24000;
  const samples = new Float32Array(Math.round(openingSeconds * rate));
  [523.251, 659.255, 783.991].forEach((frequency, note) => {
    const start = .08 + note * .1;
    for (let i = Math.ceil(start * rate); i < Math.min(samples.length, (start + .85) * rate); i++) {
      const t = i / rate - start;
      const envelope = Math.min(1, t / .008) * Math.exp(-t / .14) * Math.min(1, (.85 - t) / .015);
      samples[i] += envelope * (Math.sin(2 * Math.PI * frequency * t) + .15 * Math.sin(4 * Math.PI * frequency * t) + .05 * Math.sin(6 * Math.PI * frequency * t));
    }
  });
  const gain = 10 ** (-16 / 20) / peak(samples);
  return encodeWav(samples.map((x) => x * gain), rate);
}

export function writeOpeningAudio(deck) {
  const read = (name) => JSON.parse(fs.readFileSync(path.join(deck, name), 'utf8'));
  const write = (name, data) => fs.writeFileSync(path.join(deck, name), JSON.stringify(data, null, 2) + '\n');
  fs.writeFileSync(path.join(deck, 'audio/steps/s-intro-0.wav'), openingSound());
  const manifest = read('audio/manifest.json');
  manifest.segments['s-intro:0'] = { file: 'steps/s-intro-0.wav', dur: openingSeconds, cues: [], sync: 'manual', kind: 'imported' };
  write('audio/manifest.json', manifest);
  const timeline = read('timeline.json');
  timeline['s-intro:0'] = { dur: openingSeconds, hold: openingSeconds, lead: 0, pad_after: 0 };
  write('timeline.json', timeline);
  const report = read('out/audio-report-plus6.json');
  report.segments.unshift({ key: 's-intro:0', dur: openingSeconds, cues: [], parts: [], effects: [{ sound: 'title', at: .08 }], peakDb: -16, role: 'title-only' });
  write('out/audio-report-plus6.json', report);
}
