// 実MP4をデコードして部品の動きが残っているか検査する。
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(video, '_local/s1-components/out');
const motion = path.join(out, 'motion');
const ffdir = 'C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin';
const run = (program, args) => {
  const r = spawnSync(path.join(ffdir, program + '.exe'), args, { encoding: null, maxBuffer: 32 * 1024 * 1024 });
  assert.ifError(r.error);
  assert.equal(r.status, 0, r.stderr?.toString('utf8'));
  return r.stdout;
};
const timeline = JSON.parse(fs.readFileSync(path.join(motion, 'timeline.out.json'), 'utf8'));
assert.equal(timeline.complete, true);
const full = path.join(motion, 'full.mp4');
run('ffmpeg', ['-v', 'error', '-i', full, '-f', 'null', '-']);
const probe = JSON.parse(run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration:stream=codec_name,width,height,r_frame_rate,nb_frames', '-of', 'json', full]));
assert.equal(probe.streams[0].width, 1280);
assert.equal(probe.streams[0].height, 720);
assert.equal(probe.streams[0].r_frame_rate, '24/1');
const clips = [];
for (const s of timeline.segments.filter((s) => s.k > 0)) {
  const clip = path.join(motion, s.clip);
  const hashes = [0, Math.min(s.anim * 0.5, 1.2), Math.min(s.anim - 1 / 24, s.clipDur - 1 / 24)].map((t) => {
    const png = run('ffmpeg', ['-v', 'error', '-ss', String(Math.max(0, t)), '-i', clip, '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-']);
    assert.ok(png.length > 1000);
    return createHash('sha256').update(png).digest('hex');
  });
  assert.ok(new Set(hashes).size > 1, `${s.key}: 実MP4の中間フレームが変化`);
  const pngPath = path.join(out, `mp4-${s.slideKey}-${s.k}.png`);
  run('ffmpeg', ['-v', 'error', '-y', '-ss', String(Math.min(0.6, s.anim / 2)), '-i', clip, '-frames:v', '1', pngPath]);
  clips.push({ key: s.key, animated: true, clip: s.clip });
}
fs.writeFileSync(path.join(out, 'video-report.json'), JSON.stringify({ probe, clips, decode: 'pass' }, null, 2) + '\n');
console.log(`MP4 verified: ${probe.format.duration}s, ${probe.streams[0].nb_frames} frames, ${clips.length} animated steps`);
