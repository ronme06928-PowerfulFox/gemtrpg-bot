// 共通クレジットをデッキ内へ配置し、全編の声とSEを生成する。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderCredits } from '../common/credits.mjs';
import { prepareVoice } from './prepare-voice.mjs';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const deck = path.join(video, '01_1ラウンドの流れ');
const json = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const credits = renderCredits(json(path.join(video, 'common/credits.json')), json(path.join(deck, 'credits.json')));
const html = fs.readFileSync(path.join(deck, 'deck.html'), 'utf8');
if (!html.includes('<!-- shared-credits:start -->')) throw new Error('共通クレジットの挿入場所がない');
fs.writeFileSync(path.join(deck, 'deck.html'), html.replace(/<!-- shared-credits:start -->[\s\S]*?<!-- shared-credits:end -->/, `<!-- shared-credits:start -->\n${credits}\n<!-- shared-credits:end -->`));
fs.copyFileSync(path.join(video, 'common/credits.css'), path.join(deck, 'credits.css'));
fs.copyFileSync(path.join(video, '../assets/gemuria_logo.png'), path.join(deck, 'images/gemuria_logo.png'));
await prepareVoice(deck, process.argv[2], { boost: 6, credits: true });
