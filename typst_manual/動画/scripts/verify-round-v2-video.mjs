// 実MP4を最後までデコードし、途中の動き・音声ピーク・最後の5秒を測る。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const deck = path.join(video, '01_1ラウンドの流れ');
const out = path.join(deck, 'out/v2-sync');
const ff = 'C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin';
const run = (program, args) => {
  const r = spawnSync(path.join(ff, program + '.exe'), args, { maxBuffer: 64 * 1024 * 1024 });
  assert.ifError(r.error); assert.equal(r.status, 0, r.stderr?.toString('utf8')); return r;
};
const full = path.join(out, 'full.mp4');
const render = JSON.parse(fs.readFileSync(path.join(out, 'timeline.out.json'), 'utf8'));
assert.equal(render.complete, true);
run('ffmpeg', ['-v', 'error', '-i', full, '-f', 'null', '-']);
const probe = JSON.parse(run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration:stream=codec_name,width,height,r_frame_rate,nb_frames', '-of', 'json', full]).stdout);
const picture = probe.streams.find((s) => s.codec_name === 'h264');
assert.equal(picture.width, 1280); assert.equal(picture.height, 720); assert.equal(picture.r_frame_rate, '24/1');
assert.ok(probe.streams.some((s) => s.codec_name === 'aac'));
const frames = render.segments.reduce((n, s) => n + s.frames, 0);
assert.equal(+picture.nb_frames, frames);
const level = run('ffmpeg', ['-hide_banner', '-i', full, '-vn', '-af', 'volumedetect', '-f', 'null', '-']).stderr.toString('utf8');
const peakDb = +level.match(/max_volume: ([-\d.]+) dB/)[1];
assert.ok(peakDb < -1 && peakDb > -30);
const audio = JSON.parse(fs.readFileSync(path.join(deck, 'out/audio-report-plus6.json'), 'utf8'));
const cue = (key, index = 0) => audio.segments.find((s) => s.key === key).cues[index];
const cases = [
  ['s-slots:1', 1.75, 3.05], ['s-resolve:1', .3, .8],
  ['s-selection:1', .9, 1.1],
  ['s-selection:2', cue('s-selection:2') - .6, cue('s-selection:2') - .2],
  ['s-next:1', .4, .7],
  ['s-intro:2', cue('s-intro:2') + .1, cue('s-intro:2') + .4],
  ['s-intro:2', cue('s-intro:2', 1) + .1, cue('s-intro:2', 1) + .4],
  ['s-speed:1', cue('s-speed:1') + .42, cue('s-speed:1') + 1.62],
  ['s-power-ally:1', cue('s-power-ally:1', 3) + .42, cue('s-power-ally:1', 3) + 1.62],
  ['s-power-enemy:1', cue('s-power-enemy:1') - 1.6, cue('s-power-enemy:1') - .4],
  ['s-damage:1', cue('s-damage:1') - .5, cue('s-damage:1') + .7],
  ['s-damage:2', cue('s-damage:2') + .2, cue('s-damage:2') + .9],
  ['s-effect-timing:1', 3.55, 4.1], ['s-effect-fp:1', .1, .65],
];
const motion = [];
for (const [caseIndex, [key, before, after]] of cases.entries()) {
  const s = render.segments.find((s) => s.key === key);
  const pngs = [before, after].map((t, index) => {
    const png = run('ffmpeg', ['-v', 'error', '-ss', String(t), '-i', path.join(out, s.clip), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-']).stdout;
    fs.writeFileSync(path.join(out, `motion-${caseIndex}-${key.replace(':', '-')}-${index}.png`), png);
    return createHash('sha256').update(png).digest('hex');
  });
  assert.notEqual(pngs[0], pngs[1], `実動画の動き: ${key}`);
  motion.push({ key, before, after, changes: true });
}
const last = render.segments.at(-1);
assert.equal(last.key, 's-credits:0'); assert.equal(last.frames, 120); assert.equal(last.clipDur, 5);
const opening = render.segments[0];
assert.equal(opening.key, 's-intro:0'); assert.equal(opening.frames, 62);
const openingLevel = run('ffmpeg', ['-hide_banner', '-i', path.join(out, opening.clip), '-vn', '-af', 'volumedetect', '-f', 'null', '-']).stderr.toString('utf8');
const openingPeakDb = +openingLevel.match(/max_volume: ([-\d.]+) dB/)[1];
assert.ok(openingPeakDb > -22 && openingPeakDb < -10, '実MP4の冒頭チャイムが鳴り、クリップしない');
run('ffmpeg', ['-v', 'error', '-y', '-ss', '0.5', '-i', full, '-frames:v', '1', path.join(out, 'opening.png')]);
const changed = render.segments.filter((s) => [0, 2, 5].includes(s.i));
const previewList = path.join(out, 'sync-scenes.concat.txt');
fs.writeFileSync(previewList, changed.map((s) => `file '${path.join(out, s.clip).replaceAll('\\', '/')}'`).join('\n') + '\n');
run('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', previewList, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', path.join(out, 'sync-scenes.mp4')]);
fs.unlinkSync(previewList);
// full.mp4から最後の画面を取り出す（クリップだけの検査で済ませない）。
for (const [name, t] of [['ending-caption', last.clipStart - 1], ['credits-middle', last.clipStart + 2.5], ['credits-end', frames / 24 - .1]]) {
  run('ffmpeg', ['-v', 'error', '-y', '-ss', String(t), '-i', full, '-frames:v', '1', path.join(out, `${name}.png`)]);
}
const report = { probe, frames, peakDb, openingPeakDb, decode: 'full pass', motion, creditsSeconds: 5, timelineSeconds: render.segments.reduce((n, s) => n + s.dur, 0), encodedSeconds: +probe.format.duration };
fs.writeFileSync(path.join(out, 'video-report.json'), JSON.stringify(report, null, 2) + '\n');
console.log(`MP4: ${probe.format.duration}s, ${frames} frames, peak ${peakDb}dBFS, full decode passed`);
