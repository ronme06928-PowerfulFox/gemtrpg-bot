// 実行: node typst_manual/動画/scripts/prepare-media.mjs <egatari-studioのフォルダ>
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';

const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const deck = path.join(video, '01_1ラウンドの流れ');
const engine = process.argv[2];
assert.ok(engine, 'egatari-studioのフォルダを指定してください');
const { parseNarration } = await import(pathToFileURL(path.join(engine, 'kit/core/narration-core.mjs')));
const { inputHash } = await import(pathToFileURL(path.join(engine, 'kit/core/portable.mjs')));
const read = (p) => fs.readFileSync(p, 'utf8');
const writeJson = (p, v) => fs.writeFileSync(p, JSON.stringify(v, null, 2) + '\n');
const cues = JSON.parse(read(path.join(deck, 'sfx/cues.json')));
const narration = parseNarration(read(path.join(deck, 'narration.md')));
const ffmpeg = process.env.FFMPEG || 'ffmpeg';
const sr = 24000;
const audioDir = path.join(deck, 'audio');
const outDir = path.join(deck, 'out');
fs.mkdirSync(path.join(audioDir, 'steps'), { recursive: true });
fs.mkdirSync(outDir, { recursive: true });

function encodeWav(samples, target) {
  const data = Buffer.alloc(samples.length * 2);
  samples.forEach((v, i) => {
    assert.ok(Math.abs(v) < 1, '効果音の合成でクリップしない');
    data.writeInt16LE(Math.round(v * 32767), i * 2);
  });
  const head = Buffer.alloc(44);
  head.write('RIFF', 0); head.writeUInt32LE(36 + data.length, 4); head.write('WAVEfmt ', 8);
  head.writeUInt32LE(16, 16); head.writeUInt16LE(1, 20); head.writeUInt16LE(1, 22);
  head.writeUInt32LE(sr, 24); head.writeUInt32LE(sr * 2, 28); head.writeUInt16LE(2, 32);
  head.writeUInt16LE(16, 34); head.write('data', 36); head.writeUInt32LE(data.length, 40);
  fs.writeFileSync(target, Buffer.concat([head, data]));
}

const sounds = {};
for (const [id, source] of Object.entries(cues.sources)) {
  assert.ok(Number.isFinite(source.peakDb) && source.peakDb <= -12, '音量の上限');
  const p = spawnSync(ffmpeg, ['-v', 'error', '-i', path.join(deck, 'sfx', source.file), '-f', 'f32le', '-ar', String(sr), '-ac', '1', 'pipe:1']);
  if (p.status !== 0) throw new Error(`ffmpeg: ${p.error?.message || p.stderr.toString()}`);
  const samples = Float32Array.from({ length: p.stdout.length / 4 }, (_, i) => p.stdout.readFloatLE(i * 4));
  const peak = samples.reduce((v, x) => Math.max(v, Math.abs(x)), 0);
  assert.ok(peak > 0 && samples.length < sr * 2, '短い非無音素材を使う');
  const gain = 10 ** (source.peakDb / 20) / peak;
  samples.forEach((v, i) => { samples[i] = v * gain * Math.min(1, (samples.length - 1 - i) / (sr * 0.008)); });
  sounds[id] = samples;
}

const timeline = {};
const manifest = { segments: {} };
const minimum = {
  's-round-title:0': 4, 's-round-title:1': 8.6,
  's-start-state:1': 9.4, 's-start-state:2': 4,
  's-selection:1': 7.5,
};
for (const s of narration) {
  const key = `${s.slideKey}:${s.stepKey}`;
  const text = s.turns.map((t) => t.display).join('').replace(/\{mark:[^}]+\}|\s/g, '');
  const dur = Math.max(4, minimum[key] || 0, Math.ceil((text.length / 7 + 1) * 10) / 10);
  timeline[key] = { hold: dur, dur, lead: 0, pad_after: 0 };
  if (!cues.steps[key]) continue;
  const mix = new Float32Array(Math.round(dur * sr));
  for (const [sound, at] of cues.steps[key]) {
    assert.ok(sounds[sound] && Number.isFinite(at) && at >= 0, `不正なキュー: ${key}`);
    const start = Math.round(at * sr);
    assert.ok(start + sounds[sound].length <= mix.length, `キューが段階内に収まる: ${key}`);
    sounds[sound].forEach((v, i) => { mix[start + i] += v; });
  }
  const file = `steps/${key.replace(':', '-')}.wav`;
  encodeWav(mix, path.join(audioDir, file));
  manifest.segments[key] = { file, dur, cues: [], sync: 'none', kind: 'imported', inputHash: await inputHash(s) };
}
const keys = new Set(Object.keys(timeline));
for (const key of Object.keys(cues.steps)) assert.ok(keys.has(key), `台本のない効果音: ${key}`);
for (const slide of new Set(narration.map((s) => s.slideKey))) {
  const key = `${slide}:0`;
  if (!timeline[key]) timeline[key] = { hold: 1.2, dur: 1.2, lead: 0, pad_after: 0 };
}
writeJson(path.join(deck, 'timeline.json'), timeline);
writeJson(path.join(audioDir, 'manifest.json'), manifest);
const reel = new Float32Array(Object.keys(sounds).length * 2 * sr);
Object.values(sounds).forEach((s, n) => s.forEach((v, i) => { reel[n * 2 * sr + i] = v; }));
encodeWav(reel, path.join(outDir, 'sfx-samples.wav'));
console.log(`Media prepared: ${Object.keys(timeline).length} stages, ${Object.keys(manifest.segments).length} SFX tracks`);
