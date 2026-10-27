import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';
import { encodeWav, decodeWav, joinParts, mixEffect, peak } from './r1-audio.mjs';

export function effectTime(effect, bounds, cues) {
  assert.ok(!(effect.mark && effect.cue !== undefined), 'SEの同期点はmarkかcueの一方');
  const index = effect.mark ? bounds.findIndex((b) => b.id === effect.mark) : effect.cue;
  if (effect.mark || index !== undefined) assert.ok(Number.isInteger(index) && index >= 0 && index < cues.length, 'SEの同期点がない');
  const at = (index !== undefined ? cues[index] : effect.at) + (effect.offset || 0);
  assert.ok(Number.isFinite(at) && at >= 0, 'SEの時刻が不正');
  return at;
}

export async function prepareVoice(deck, engine, { boost = 6, credits = false } = {}) {
  assert.ok(engine, 'egatari-studioのパスが必要です');
  const { parseNarration } = await import(pathToFileURL(path.join(engine, 'kit/core/narration-core.mjs')));
  const { inputHash } = await import(pathToFileURL(path.join(engine, 'kit/core/portable.mjs')));
  const readJson = (p) => JSON.parse(fs.readFileSync(path.join(deck, p), 'utf8'));
  const writeJson = (p, v) => fs.writeFileSync(path.join(deck, p), JSON.stringify(v, null, 2) + '\n');
  const config = readJson('voice/config.json');
  const events = readJson('voice/events.json');
  const source = readJson('sfx/cues.json').sources;
  const sr = 24000;
  const endpoint = process.env.VOICEVOX_URL || 'http://127.0.0.1:50021';
  assert.ok(/^http:\/\/127\.0\.0\.1:\d+$/.test(endpoint), 'ローカルのVOICEVOXだけを使用する');
  const ffmpeg = process.env.FFMPEG || 'ffmpeg';
  for (const dir of ['voice/cache', 'audio/steps', 'out']) fs.mkdirSync(path.join(deck, dir), { recursive: true });
  const request = async (url, init) => {
    const r = await fetch(endpoint + url, { ...init, signal: AbortSignal.timeout(180000) });
    if (!r.ok) throw new Error(`VOICEVOX ${r.status}: ${await r.text()}`);
    return r;
  };
  const version = await (await request('/version')).json();
  assert.equal(version, config.engineVersion, 'VOICEVOXの固定版と一致する');
  const speakers = await (await request('/speakers')).json();
  const speaker = speakers.find((s) => s.name === config.speaker);
  const style = speaker?.styles.find((s) => s.name === config.style);
  assert.ok(style, '冥鳴ひまりのスタイルが見つからない');
  const segments = parseNarration(fs.readFileSync(path.join(deck, 'narration.md'), 'utf8'));
  const identity = { version, speaker: speaker.name, speakerUuid: speaker.speaker_uuid, style: style.name, styleId: style.id };
  const run = (args, input) => {
    const p = spawnSync(ffmpeg, ['-v', 'error', ...args], { input, maxBuffer: 32 * 1024 * 1024 });
    if (p.status !== 0) throw new Error(p.error?.message || p.stderr.toString());
    return p.stdout;
  };
  const floats = (b) => Float32Array.from({ length: b.length / 4 }, (_, i) => b.readFloatLE(i * 4));
  const normalizeVoice = (a) => {
    const b = Buffer.alloc(a.length * 4);
    a.forEach((x, i) => b.writeFloatLE(x, i * 4));
    const normalized = floats(run(['-f', 'f32le', '-ar', String(sr), '-ac', '1', '-i', 'pipe:0', '-af', 'loudnorm=I=-20:TP=-3:LRA=7', '-f', 'f32le', '-ar', String(sr), '-ac', '1', 'pipe:1'], b));
    assert.ok(Math.abs(normalized.length - a.length) < sr * 0.02, '音量調整で音声長を変えない');
    const result = new Float32Array(a.length);
    result.set(normalized.subarray(0, a.length));
    return result;
  };
  const sounds = {};
  for (const [name, s] of Object.entries(source)) {
    const a = floats(run(['-i', path.join(deck, 'sfx', s.file), '-f', 'f32le', '-ar', String(sr), '-ac', '1', 'pipe:1']));
    const gain = 10 ** ((s.peakDb + boost) / 20) / peak(a);
    sounds[name] = a.map((x, i) => x * gain * Math.min(1, (a.length - 1 - i) / (sr * 0.008)));
  }
  const timing = {};
  const manifest = { segments: {} };
  const report = { voice: identity, seBoostDb: boost, segments: [] };
  let cacheHits = 0;
  let made = 0;
  for (const s of segments) {
    const key = `${s.slideKey}:${s.stepKey}`;
    const event = events[key];
    assert.ok(event, `段階の設定がない: ${key}`);
    const parts = s.turns.flatMap((t) => t.ttsParts);
    const arrays = [];
    const partLog = [];
    for (const part of parts) {
      if (!part.trim()) { arrays.push(null); continue; }
      let text = part;
      for (const [display, reading] of Object.entries(config.readings)) text = text.replaceAll(display, reading);
      const settings = Object.fromEntries(['speedScale', 'pitchScale', 'intonationScale', 'prePhonemeLength', 'postPhonemeLength'].map((k) => [k, config[k]]));
      const hash = createHash('sha256').update(JSON.stringify({ identity, text, settings })).digest('hex');
      const wavFile = path.join(deck, 'voice/cache', `${hash}.wav`);
      partLog.push({ text, hash, cached: fs.existsSync(wavFile) });
      if (fs.existsSync(wavFile)) cacheHits++;
      else {
        const query = await (await request(`/audio_query?speaker=${style.id}&text=${encodeURIComponent(text)}`, { method: 'POST' })).json();
        Object.assign(query, settings, { outputSamplingRate: sr, outputStereo: false });
        const bytes = Buffer.from(await (await request(`/synthesis?speaker=${style.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(query) })).arrayBuffer());
        decodeWav(bytes);
        fs.writeFileSync(wavFile, bytes);
        fs.writeFileSync(wavFile.replace('.wav', '.json'), JSON.stringify({ identity, text, query }, null, 2) + '\n');
        made++;
      }
      const wav = decodeWav(fs.readFileSync(wavFile));
      assert.equal(wav.rate, sr);
      arrays.push(wav.samples);
    }
    const joined = joinParts(arrays, sr, config.partGap);
    assert.equal(joined.cues.length, s.bounds.length, `markの数が一致: ${key}`);
    const dur = Math.ceil((joined.samples.length / sr + event.tail) * 100) / 100;
    const mix = new Float32Array(Math.round(dur * sr));
    mix.set(normalizeVoice(joined.samples));
    const cues = joined.cues.map((x) => +x.toFixed(4));
    const effectLog = [];
    for (const effect of event.effects) {
      const at = effectTime(effect, s.bounds, cues);
      mixEffect(mix, sounds[effect.sound], Math.round(at * sr));
      effectLog.push({ sound: effect.sound, at });
    }
    assert.ok(peak(mix) < 0.95, `合成後に余裕がない: ${key}`);
    const file = `steps/${key.replace(':', '-')}.wav`;
    fs.writeFileSync(path.join(deck, 'audio', file), encodeWav(mix, sr));
    manifest.segments[key] = { file, dur, cues, sync: 'manual', kind: 'imported', inputHash: await inputHash(s) };
    timing[key] = { hold: dur, dur, lead: 0, pad_after: 0 };
    report.segments.push({ key, dur, cues, parts: partLog, effects: effectLog, peakDb: 20 * Math.log10(peak(mix)) });
    console.log(`${key}: ${dur.toFixed(2)}s`);
  }
  for (const id of new Set(segments.map((s) => s.slideKey))) timing[`${id}:0`] ??= { dur: 0.6, hold: 0.6 };
  if (credits) timing['s-credits:0'] = { dur: 5, hold: 5, lead: 0, pad_after: 0 };
  writeJson('timeline.json', timing);
  writeJson('audio/manifest.json', manifest);
  writeJson(`out/audio-report${boost ? '-plus6' : '-baseline'}.json`, report);
  console.log(`VOICEVOX ${version} ${speaker.name}/${style.name} (${style.id}): new ${made}, cache ${cacheHits}, SE +${boost}dB`);
}
