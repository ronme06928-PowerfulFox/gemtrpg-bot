// R1の比較用。全編と同じ音声生成処理を使う。
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { prepareVoice } from './prepare-voice.mjs';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
await prepareVoice(path.join(video, '01_1ラウンドの流れ_R1'), process.argv[2], { boost: process.argv.includes('--baseline') ? 0 : 6 });
